#!/usr/bin/env python3
"""Read-only validation of a frozen B02 candidate, or report the DWG gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "service" / "src"))

import ezdxf
import pymupdf as fitz
from pypdf import PdfReader

from heater_drawing.domain.models import DrawingPage
from heater_drawing.drawing.dwg_adapter import capabilities
from heater_drawing.drawing.dxf_writer import expected_text_records
from heater_drawing.drawing.fonts import check_glyph_coverage, prepare_runtime_font
from heater_drawing.drawing.pdf_renderer import render_page
from heater_drawing.drawing.readback import inspect_dxf
from heater_drawing.drawing.sample import load_sample
from heater_drawing.drawing.template import load_template, sha256_file


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tree_hashes(directory: Path) -> dict[str, str]:
    return {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in sorted(directory.rglob("*")) if path.is_file()}


def pdf_font_names(path: Path) -> list[str]:
    names: set[str] = set()
    for page in PdfReader(str(path)).pages:
        resources = page.get("/Resources", {})
        fonts = resources.get("/Font", {})
        for reference in fonts.values():
            font = reference.get_object()
            name = str(font.get("/BaseFont", "")).lstrip("/")
            if "+" in name:
                name = name.split("+", 1)[1]
            names.add(name)
    return sorted(names)


def validate_pdf_page(path: Path, page_plan, layout: dict) -> dict:
    reader = PdfReader(str(path))
    if len(reader.pages) != 1:
        raise ValueError(f"single-page PDF page count drift: {path}")
    page = reader.pages[0]
    width_mm = float(page.mediabox.width) * 25.4 / 72.0
    height_mm = float(page.mediabox.height) * 25.4 / 72.0
    if abs(width_mm - 210.0) > 0.1 or abs(height_mm - 297.0) > 0.1:
        raise ValueError(f"PDF paper size drift: {page_plan.code}")
    extracted = page.extract_text() or ""
    compact_extracted = re.sub(r"\s+", "", extracted)
    missing = [
        record["text"]
        for record in expected_text_records(layout, page_plan)
        if re.sub(r"\s+", "", record["text"]) not in compact_extracted
    ]
    if missing:
        raise ValueError(f"PDF content does not match DrawingPage/DXF for {page_plan.code}: {missing[:3]}")
    resources = page.get("/Resources", {})
    xobjects = resources.get("/XObject", {})
    images = [name for name, ref in xobjects.items() if ref.get_object().get("/Subtype") == "/Image"]
    if images:
        raise ValueError(f"PDF contains unexpected raster images: {page_plan.code}")
    contents = page.get_contents()
    content_bytes = contents.get_data() if contents is not None else b""
    if len(content_bytes) < 1000:
        raise ValueError(f"PDF vector content is unexpectedly empty: {page_plan.code}")
    return {"page_mm": [width_mm, height_mm], "expected_text_entities": len(expected_text_records(layout, page_plan)),
            "extracted_text_sha256": __import__("hashlib").sha256(extracted.encode("utf-8")).hexdigest(),
            "raster_images": 0, "content_stream_bytes": len(content_bytes)}


def _rendered_pdf_samples(path: Path, page_index: int = 0, scale: float = 4.0) -> tuple[int, int, bytes]:
    document = fitz.open(path)
    if page_index >= len(document):
        raise ValueError(f"PDF page index is unavailable: {path}: {page_index}")
    pixmap = document[page_index].get_pixmap(
        matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False
    )
    return pixmap.width, pixmap.height, pixmap.samples


def compare_visible_pdf(candidate: Path, canonical: Path, *, candidate_page: int = 0) -> dict:
    actual = _rendered_pdf_samples(candidate, candidate_page)
    expected = _rendered_pdf_samples(canonical)
    if actual[:2] != expected[:2]:
        raise ValueError(f"PDF visible render dimensions drift: {candidate}")
    changed_channels = sum(left != right for left, right in zip(actual[2], expected[2]))
    if changed_channels:
        raise ValueError(
            f"PDF visible geometry differs from canonical DXF render: {candidate}: "
            f"{changed_channels}/{len(expected[2])} channels"
        )
    return {
        "raster_scale": 4.0,
        "width_px": actual[0],
        "height_px": actual[1],
        "changed_channels": 0,
        "paper_tolerance_mm": 0.1,
    }


def validate_pdf_dimension_text_vectors(
    path: Path,
    measurements: dict[str, dict],
    page_index: int = 0,
    tolerance_mm: float = 0.03,
) -> dict:
    """Compare final PDF ink with native Noto DIMENSION cache glyph bounds."""
    page = fitz.open(path)[page_index]
    drawings = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if fill is None or any(float(channel) > 0.01 for channel in fill):
            continue
        rect = drawing["rect"]
        drawings.append(
            [
                rect.x0 * 25.4 / 72.0,
                (page.rect.height - rect.y1) * 25.4 / 72.0,
                rect.x1 * 25.4 / 72.0,
                (page.rect.height - rect.y0) * 25.4 / 72.0,
            ]
        )
    results = {}
    for kind, measurement in measurements.items():
        expected = [float(value) for value in measurement["box_paper_mm"]]
        found = [
            box
            for box in drawings
            if box[0] >= expected[0] - tolerance_mm
            and box[1] >= expected[1] - tolerance_mm
            and box[2] <= expected[2] + tolerance_mm
            and box[3] <= expected[3] + tolerance_mm
        ]
        if not found:
            raise ValueError(f"PDF native dimension glyph vectors are missing: {path}: {kind}")
        actual = [
            min(box[0] for box in found),
            min(box[1] for box in found),
            max(box[2] for box in found),
            max(box[3] for box in found),
        ]
        max_error = max(abs(a - b) for a, b in zip(actual, expected, strict=True))
        if max_error > tolerance_mm:
            raise ValueError(
                f"PDF native dimension glyph scale/position drift: {path}: {kind}: {max_error}"
            )
        expected_width = expected[2] - expected[0]
        expected_height = expected[3] - expected[1]
        results[kind] = {
            "text": measurement["text"],
            "style": measurement["style"],
            "native_cache_box_paper_mm": expected,
            "actual_pdf_vector_box_paper_mm": actual,
            "actual_to_native_width_ratio": (actual[2] - actual[0]) / expected_width,
            "actual_to_native_height_ratio": (actual[3] - actual[1]) / expected_height,
            "max_edge_error_mm": max_error,
            "visible_vector_count": len(found),
        }
    return {
        "status": "passed",
        "comparison": "native HEATER_CJK Noto cache versus final PDF visible vector fills",
        "tolerance_mm": tolerance_mm,
        "dimensions": results,
    }


def _pdf_segment_error(
    actual: tuple[tuple[float, float], tuple[float, float]],
    expected: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    def point_error(left, right) -> float:
        return math.hypot(left[0] - right[0], left[1] - right[1])

    direct = max(point_error(actual[0], expected[0]), point_error(actual[1], expected[1]))
    reverse = max(point_error(actual[0], expected[1]), point_error(actual[1], expected[0]))
    return min(direct, reverse)


def validate_pdf_frame_colors(
    path: Path,
    layout: dict,
    *,
    page_index: int = 0,
    tolerance_mm: float = 0.05,
) -> dict:
    yellow_true_color = 16308017
    yellow_rgb = tuple(round(component / 255.0, 6) for component in (0xF8, 0xD7, 0x31))
    black_rgb = (0.0, 0.0, 0.0)
    document = fitz.open(path)
    if page_index >= len(document):
        raise ValueError(f"PDF page index is unavailable for frame-color validation: {path}")
    page = document[page_index]
    height_mm = float(page.rect.height) * 25.4 / 72.0
    segments = []
    for drawing in page.get_drawings():
        color = drawing.get("color")
        if color is None:
            continue
        rgb = tuple(round(float(component), 6) for component in color)
        for item in drawing.get("items", []):
            if item[0] != "l":
                continue
            first, second = item[1], item[2]
            segments.append(
                {
                    "points": (
                        (float(first.x) * 25.4 / 72.0, height_mm - float(first.y) * 25.4 / 72.0),
                        (float(second.x) * 25.4 / 72.0, height_mm - float(second.y) * 25.4 / 72.0),
                    ),
                    "rgb": rgb,
                }
            )
    expected_segments = [
        {
            "points": ((float(line[0]), float(line[1])), (float(line[2]), float(line[3]))),
            "layer": str(line[4]),
            "role": "yellow" if line[6] == yellow_true_color else "black",
            "rgb": yellow_rgb if line[6] == yellow_true_color else black_rgb,
        }
        for line in layout["frame_lines_mm"]
    ]
    results = []
    for expected in expected_segments:
        matches = sorted(
            (
                (_pdf_segment_error(actual["points"], expected["points"]), actual)
                for actual in segments
            ),
            key=lambda pair: pair[0],
        )
        if not matches or matches[0][0] > tolerance_mm:
            raise ValueError(f"PDF controlled frame segment is missing: {path}: {expected['points']}")
        error, actual = matches[0]
        if actual["rgb"] != expected["rgb"]:
            raise ValueError(
                f"PDF controlled frame color drift: {path}: {expected['layer']} "
                f"expected {expected['rgb']}, found {actual['rgb']}"
            )
        results.append(
            {
                "layer": expected["layer"],
                "role": expected["role"],
                "expected_rgb": expected["rgb"],
                "actual_rgb": actual["rgb"],
                "coordinate_error_mm": error,
            }
        )
    return {
        "checked_segments": len(results),
        "yellow_segments": sum(item["role"] == "yellow" for item in results),
        "black_segments": sum(item["role"] == "black" for item in results),
        "max_coordinate_error_mm": max(item["coordinate_error_mm"] for item in results),
        "tolerance_mm": tolerance_mm,
        "segments": results,
    }


def _normalize_semantic_floats(value):
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, dict):
        return {key: _normalize_semantic_floats(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_semantic_floats(item) for item in value]
    return value


def page_consistency_signature(page: dict) -> dict:
    signature = {
        key: page[key]
        for key in (
            "row_id",
            "code",
            "geometry_mm",
            "native_dimensions_mm",
            "scale",
            "geometry_lead_dimension_box_paper_mm",
            "complete_content_box_paper_mm",
            "text_measurements",
            "controlled_layer_display",
            "dimension_parent_display",
            "dimension_linetype_sources",
            "dimension_cache_semantics",
            "dimension_text_measurements",
        )
    }
    return _normalize_semantic_floats(signature)


def probe_dwg(output: Path) -> int:
    converter = os.environ.get("HEATER_DWG_CONVERTER")
    license_record = os.environ.get("HEATER_DWG_LICENSE_RECORD")
    result = capabilities(Path(converter) if converter else None, Path(license_record) if license_record else None)
    payload = {
        "profile": "dwg_candidate", "status": "blocked" if result.state not in {"verified_evaluation_only", "production_ready"} else "available_verified_evaluation_only",
        "conversion_run": False, "capability": result.to_dict(),
        "approval_claim": "none",
        "policy": "No converter is invoked without this project's authorization and stored round-trip evidence.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    write_json(output / "capability.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "available_verified_evaluation_only" else 2


def probe_candidate(fixture: Path, candidate: Path, output: Path) -> int:
    before = tree_hashes(candidate)
    template_dir = ROOT / "templates" / "heater-a4-v1"
    template_before = tree_hashes(template_dir)
    template = load_template(template_dir)
    manifest = json.loads((candidate / "candidate-manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["artifact_hashes"].items():
        path = ROOT / name
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"frozen candidate hash mismatch: {name}")
    if manifest["fixture_sha256"] != sha256_file(fixture):
        raise ValueError("candidate fixture binding mismatch")
    expected_template = manifest["template"]
    actual_template = {
        "manifest_sha256": sha256_file(template_dir / "manifest.json"),
        "layout_sha256": template["layout_sha256"], "fonts_sha256": template["fonts_sha256"],
        "template_dxf_sha256": template["template_sha256"],
    }
    if expected_template != actual_template:
        raise ValueError("candidate template binding mismatch")
    fixture_data, pages = load_sample(fixture, template_dir)
    planned = [DrawingPage.model_validate(item) for item in json.loads((candidate / "drawing-pages.json").read_text(encoding="utf-8"))]
    if [item.model_dump(mode="json") for item in planned] != [item.model_dump(mode="json") for item in pages]:
        raise ValueError("candidate DrawingPage plan drift")
    combined = inspect_dxf(candidate / "heater-sample.dxf", pages, template["layout"], template["fonts"])
    all_texts: list[str] = []
    page_reports = []
    embedded_fonts: dict[str, list[str]] = {}
    pdf_semantics: dict[str, dict] = {}
    single_combined_consistency: dict[str, dict] = {}
    font_path = prepare_runtime_font(template["fonts"], ROOT)
    merged_path = candidate / "heater-sample.pdf"
    with tempfile.TemporaryDirectory(prefix="heater-pdf-probe-") as temporary:
        temporary_root = Path(temporary)
        for index, page in enumerate(pages):
            dxf = candidate / "pages" / f"{page.code}.dxf"
            pdf = candidate / "pages" / f"{page.code}.pdf"
            report = inspect_dxf(dxf, [page], template["layout"], template["fonts"])
            document = ezdxf.readfile(dxf)
            all_texts.extend(entity.dxf.text for entity in document.modelspace().query("TEXT"))
            names = pdf_font_names(pdf)
            if not any("NotoSansCJKsc-Regular" in name for name in names):
                raise ValueError(f"PDF does not embed locked SC face identity: {page.code}: {names}")
            embedded_fonts[page.code] = names
            canonical_pdf = temporary_root / f"{page.code}.pdf"
            canonical_png = temporary_root / f"{page.code}.png"
            render_page(
                dxf, canonical_pdf, canonical_png, float(page.scale.denominator),
                font_path, template["fonts"],
            )
            semantics = validate_pdf_page(pdf, page, template["layout"])
            semantics["frame_color_semantics"] = validate_pdf_frame_colors(
                pdf, template["layout"]
            )
            dimension_measurements = report["pages"][0]["dimension_text_measurements"]
            semantics["dimension_text_vectors"] = validate_pdf_dimension_text_vectors(
                pdf, dimension_measurements
            )
            semantics["merged_dimension_text_vectors"] = validate_pdf_dimension_text_vectors(
                merged_path, dimension_measurements, page_index=index
            )
            semantics["merged_frame_color_semantics"] = validate_pdf_frame_colors(
                merged_path, template["layout"], page_index=index
            )
            semantics["visible_dxf_equivalence"] = compare_visible_pdf(pdf, canonical_pdf)
            semantics["merged_page_equivalence"] = compare_visible_pdf(
                merged_path, canonical_pdf, candidate_page=index
            )
            pdf_semantics[page.code] = semantics
            page_reports.append({"code": page.code, "readback": report})
            single_page = page_consistency_signature(report["pages"][0])
            combined_page = page_consistency_signature(combined["pages"][index])
            if single_page != combined_page:
                raise ValueError(f"single-page and combined DXF semantics differ: {page.code}")
            single_combined_consistency[page.code] = {
                "status": "passed",
                "normalized_page_semantics": single_page,
            }
    glyphs = check_glyph_coverage(font_path, all_texts + ["25 30 50 100 300"])
    merged_reader = PdfReader(str(merged_path))
    if len(merged_reader.pages) != len(pages):
        raise ValueError("merged PDF page count drift")
    for index, page_plan in enumerate(pages):
        merged_text = merged_reader.pages[index].extract_text() or ""
        if page_plan.code not in merged_text or page_plan.fields.name not in merged_text:
            raise ValueError(f"merged PDF page order/content drift: {page_plan.code}")
    after = tree_hashes(candidate)
    template_after = tree_hashes(template_dir)
    if before != after or template_before != template_after:
        raise ValueError("read-only validation mutated candidate or controlled template bytes")
    payload = {
        "profile": "dxf_pdf_v1", "status": "passed", "candidate": candidate.relative_to(ROOT).as_posix(),
        "candidate_built_at": manifest["built_at"],
        "candidate_manifest_sha256": sha256_file(candidate / "candidate-manifest.json"),
        "candidate_immutable": True, "template_immutable": True, "dxf": combined,
        "pages": page_reports, "glyph_coverage": glyphs, "pdf_embedded_fonts": embedded_fonts,
        "pdf_semantics": pdf_semantics, "single_combined_consistency": single_combined_consistency,
        "validated_candidate_hashes": before, "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    write_json(output / "probe-result.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--profile", choices=("dxf_pdf_v1", "dwg_candidate"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()
    if not output.is_relative_to((ROOT / "docs" / "evidence").resolve()):
        parser.error("output must stay in docs/evidence")
    if args.profile == "dwg_candidate":
        return probe_dwg(output)
    if args.fixture is None or args.candidate is None:
        parser.error("dxf_pdf_v1 requires --fixture and --candidate")
    fixture = (ROOT / args.fixture).resolve() if not args.fixture.is_absolute() else args.fixture.resolve()
    candidate = (ROOT / args.candidate).resolve() if not args.candidate.is_absolute() else args.candidate.resolve()
    if not fixture.is_relative_to(ROOT) or not candidate.is_relative_to((ROOT / "docs" / "evidence").resolve()):
        parser.error("fixture/candidate must stay inside the project evidence boundary")
    return probe_candidate(fixture, candidate, output)


if __name__ == "__main__":
    raise SystemExit(main())
