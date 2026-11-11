#!/usr/bin/env python3
"""Explicitly build a new B02 candidate; validation is a separate read-only step."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "service" / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import ezdxf
import pymupdf as fitz

from heater_drawing.drawing.dxf_writer import expected_text_records, write_combined_dxf, write_page_dxf
from heater_drawing.drawing.fonts import check_glyph_coverage, prepare_runtime_font
from heater_drawing.drawing.pdf_renderer import merge_pdfs, render_page
from heater_drawing.drawing.readback import inspect_dxf
from heater_drawing.drawing.sample import load_sample
from heater_drawing.drawing.template import load_template, sha256_file, write_manifest


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _segment_length(segment: list[float]) -> float:
    return math.hypot(segment[2] - segment[0], segment[3] - segment[1])


def _segment_match(candidate: list[float], source: list[float]) -> tuple[float, float, float] | None:
    candidate_vertical = abs(candidate[0] - candidate[2]) <= 0.15
    source_vertical = abs(source[0] - source[2]) <= 0.15
    if candidate_vertical != source_vertical:
        return None
    candidate_length = _segment_length(candidate)
    source_length = _segment_length(source)
    if candidate_length <= 0 or abs(source_length - candidate_length) > max(0.5, candidate_length * 0.02):
        return None
    if candidate_vertical:
        coordinate_delta = abs((candidate[0] + candidate[2] - source[0] - source[2]) / 2)
        overlap = max(0.0, min(max(candidate[1], candidate[3]), max(source[1], source[3])) - max(min(candidate[1], candidate[3]), min(source[1], source[3])))
    else:
        coordinate_delta = abs((candidate[1] + candidate[3] - source[1] - source[3]) / 2)
        overlap = max(0.0, min(max(candidate[0], candidate[2]), max(source[0], source[2])) - max(min(candidate[0], candidate[2]), min(source[0], source[2])))
    coverage = overlap / candidate_length
    endpoint_delta = min(
        math.hypot(candidate[0] - source[0], candidate[1] - source[1]) + math.hypot(candidate[2] - source[2], candidate[3] - source[3]),
        math.hypot(candidate[0] - source[2], candidate[1] - source[3]) + math.hypot(candidate[2] - source[0], candidate[3] - source[1]),
    )
    if coverage < 0.95 or coordinate_delta > 2.0:
        return None
    return coordinate_delta, endpoint_delta, coverage


def measure_reference(reference_pdf: Path, layout: dict, pages: list) -> dict:
    document = fitz.open(reference_pdf)
    scale = 25.4 / 72.0
    outer = layout["outer_border_mm"]
    candidates = [
        [outer["left"], outer["bottom"], outer["right"], outer["bottom"], "outer-bottom"],
        [outer["right"], outer["bottom"], outer["right"], outer["top"], "outer-right"],
        [outer["right"], outer["top"], outer["left"], outer["top"], "outer-top"],
        [outer["left"], outer["top"], outer["left"], outer["bottom"], "outer-left"],
        *[list(line[:4]) + [f"frame-{index}"] for index, line in enumerate(layout["frame_lines_mm"])],
    ]
    page_reports = []
    for page_index, (source_page, page_plan) in enumerate(zip(document, pages, strict=True)):
        page_height = source_page.rect.height * scale
        source_lines = []
        for drawing in source_page.get_drawings():
            for item in drawing["items"]:
                if item[0] != "l":
                    continue
                start, end = item[1], item[2]
                line = [start.x * scale, page_height - start.y * scale, end.x * scale, page_height - end.y * scale]
                if (abs(line[0] - line[2]) <= 0.15 or abs(line[1] - line[3]) <= 0.15) and _segment_length(line) >= 5.0:
                    source_lines.append(line)
        available = set(range(len(source_lines)))
        comparisons = []
        for x1, y1, x2, y2, name in candidates:
            candidate = [x1, y1, x2, y2]
            options = []
            for source_index in available:
                score = _segment_match(candidate, source_lines[source_index])
                if score is not None:
                    options.append((score, source_index))
            if options:
                score, source_index = min(options)
                available.remove(source_index)
                source = source_lines[source_index]
                status = "matched" if score[0] <= 0.15 and score[1] <= 0.5 else "relayout"
            else:
                score, source, status = None, None, "candidate_added_or_source_deleted"
            comparisons.append({
                "id": name, "status": status, "candidate_segment_mm": candidate,
                "source_segment_mm": source,
                "coordinate_delta_mm": score[0] if score else None,
                "endpoint_delta_mm": score[1] if score else None,
                "overlap_coverage": score[2] if score else None,
                "uncertainty_mm": 0.15,
            })
        text_comparisons = []
        for record in expected_text_records(layout, page_plan):
            if record["kind"] == "fixed":
                status = "verified_from_original_dwg_template"
                reason = "value, entity type, style, and anchor are preserved from the hash-bound native template DXF"
                source = "original DWG -> authorized one-time ODA DXF conversion"
            elif record["kind"] == "field":
                status = "verified_from_excel_and_dxf_readback"
                reason = "value is bound from the reviewed Excel fixture and exact editable DXF readback"
                source = "fixtures/case/加热器图纸.xlsx via fixtures/synthetic/heater_sample.json"
            else:
                status = "verified_from_generator_inputs_and_dxf_readback"
                reason = "controlled wording plus Excel resistance, tolerance, and quantity values were read back exactly"
                source = "technical_lines() controlled wording plus reviewed Excel fixture"
            text_comparisons.append({
                "id": f"{record['kind']}-{record['id']}",
                "text": record["text"],
                "candidate_point_mm": record["point_mm"],
                "status": status,
                "source": source,
                "reason": reason,
                "reference_pdf_semantic_limit": "reference PDF text is vector outlines; visible crop comparison is separate evidence",
                "engineering_approval": "pending",
            })
        page_reports.append({
            "page": page_index + 1, "code": page_plan.code,
            "line_comparisons": comparisons,
            "source_unmatched_segments_mm": [source_lines[index] for index in sorted(available)],
            "text_comparisons": text_comparisons,
        })
    return {
        "source": str(reference_pdf), "source_sha256": sha256_file(reference_pdf),
        "source_pages": len(document),
        "transform": "PDF points x 25.4/72; y_candidate = page_height_mm - y_pdf",
        "line_detection_tolerance_mm": 0.15, "minimum_source_segment_mm": 5.0,
        "matching": "one-to-one orientation, complete length, endpoints, overlap coverage, and coordinate delta",
        "pages": page_reports,
        "approval_note": "PDF vector measurements are reconstruction evidence, not original DWG coordinates; all re-layout remains pending engineering approval.",
    }


def build_difference_pdf(path: Path, measurements: dict, font_path: Path) -> None:
    def segment_text(segment: list[float] | None) -> str:
        if segment is None:
            return "none"
        return (
            f"[{segment[0]:.3f}, {segment[1]:.3f}] -> "
            f"[{segment[2]:.3f}, {segment[3]:.3f}]"
        )

    rows: list[tuple[str, str, str, str, str, str]] = []
    for page in measurements["pages"]:
        for item in page["line_comparisons"]:
            delta = "n/a" if item["coordinate_delta_mm"] is None else f"{item['coordinate_delta_mm']:.3f}"
            rows.append((
                page["code"], item["id"], item["status"], delta,
                segment_text(item["candidate_segment_mm"]),
                segment_text(item["source_segment_mm"]),
            ))
        for index, segment in enumerate(page["source_unmatched_segments_mm"]):
            rows.append((
                page["code"], f"source-unmatched-{index}", "source_unmatched", "n/a",
                "none", segment_text(segment),
            ))
        for item in page["text_comparisons"]:
            rows.append((
                page["code"], item["id"], item["status"], "pending", item["text"],
                item["source"],
            ))

    wrap_widths = (8, 22, 19, 9, 38, 38)
    displayed = [
        [textwrap.fill(str(value), width=wrap_widths[column]) for column, value in enumerate(row)]
        for row in rows
    ]
    row_units = [max(value.count("\n") + 1 for value in row) for row in displayed]
    pages: list[tuple[list[list[str]], list[int]]] = []
    page_rows: list[list[str]] = []
    page_units: list[int] = []
    for row, units in zip(displayed, row_units, strict=True):
        if page_rows and sum(page_units) + units > 45:
            pages.append((page_rows, page_units))
            page_rows, page_units = [], []
        page_rows.append(row)
        page_units.append(units)
    if page_rows:
        pages.append((page_rows, page_units))

    font = FontProperties(fname=str(font_path), size=5.5)
    title_font = FontProperties(fname=str(font_path), size=10)
    from matplotlib.backends.backend_pdf import PdfPages
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path, metadata={"Title": "B02 measured reference/candidate differences"}) as pdf:
        for page_number, (page_rows, page_units) in enumerate(pages, start=1):
            fig, ax = plt.subplots(figsize=(11.69, 8.27))
            ax.axis("off")
            table = ax.table(
                cellText=page_rows,
                colLabels=["page", "item", "status", "delta mm", "candidate / value", "source / evidence"],
                colWidths=[0.07, 0.15, 0.14, 0.08, 0.28, 0.28],
                bbox=[0.0, 0.02, 1.0, 0.92],
                cellLoc="left",
            )
            table.auto_set_font_size(False)
            total_units = 1.25 + sum(page_units)
            for (row_index, _), cell in table.get_celld().items():
                units = 1.25 if row_index == 0 else page_units[row_index - 1]
                cell.set_height(0.92 * units / total_units)
                cell.get_text().set_fontproperties(font)
                cell.get_text().set_fontsize(5.5)
                cell.PAD = 0.08
            ax.set_title(
                "Measured PDF vector coordinates and candidate re-layout "
                f"(uncertainty +/-0.15 mm) - {page_number}/{len(pages)}",
                fontproperties=title_font,
            )
            pdf.savefig(fig)
            plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refresh-template", action="store_true")
    args = parser.parse_args()
    fixture = (ROOT / args.fixture).resolve() if not args.fixture.is_absolute() else args.fixture.resolve()
    output = (ROOT / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()
    evidence_root = (ROOT / "docs" / "evidence").resolve()
    if not fixture.is_relative_to(ROOT) or not output.is_relative_to(evidence_root):
        parser.error("fixture and output must stay inside the project")
    if output.exists() and any(output.iterdir()):
        parser.error("candidate output must be a new empty directory")
    template_dir = ROOT / "templates" / "heater-a4-v1"
    layout = json.loads((template_dir / "layout.json").read_text(encoding="utf-8"))
    fonts = json.loads((template_dir / "fonts.json").read_text(encoding="utf-8"))
    font_path = prepare_runtime_font(fonts, ROOT)
    if args.refresh_template:
        from refresh_native_template import refresh
        refresh(
            ROOT / layout["source_template"]["evidence_path"],
            template_dir,
        )
        layout = json.loads((template_dir / "layout.json").read_text(encoding="utf-8"))
        write_manifest(template_dir)
    template = load_template(template_dir)
    fixture_data, pages = load_sample(fixture, template_dir)
    output.mkdir(parents=True, exist_ok=True)
    combined = output / "heater-sample.dxf"
    write_combined_dxf(combined, pages, layout, fonts)
    page_reports = []
    page_pdfs = []
    artifacts = [combined]
    generated_texts: list[str] = []
    for page in pages:
        page_dxf = output / "pages" / f"{page.code}.dxf"
        page_pdf = output / "pages" / f"{page.code}.pdf"
        page_png = output / "renders" / f"{page.code}.png"
        write_page_dxf(page_dxf, page, layout, fonts)
        readback = inspect_dxf(page_dxf, [page], layout)
        document = ezdxf.readfile(page_dxf)
        generated_texts.extend(
            entity.plain_text() if entity.dxftype() == "MTEXT" else entity.dxf.text
            for entity in document.modelspace().query("TEXT MTEXT")
        )
        render = render_page(page_dxf, page_pdf, page_png, float(page.scale.denominator), font_path, fonts)
        page_pdfs.append(page_pdf)
        artifacts.extend([page_dxf, page_pdf, page_png])
        page_reports.append({"row_id": page.row_id, "code": page.code, "readback": readback, "render": render})
    merged = output / "heater-sample.pdf"
    merge_pdfs(page_pdfs, merged)
    artifacts.append(merged)
    difference_pdf = output / "reference-difference.pdf"
    measurements = measure_reference(ROOT / "fixtures" / "case" / "加热器图纸.pdf", layout, pages)
    measurements_path = output / "reference-measurements.json"
    write_json(measurements_path, measurements)
    build_difference_pdf(difference_pdf, measurements, font_path)
    artifacts.append(difference_pdf)
    artifacts.append(measurements_path)
    glyphs = check_glyph_coverage(font_path, generated_texts + ["25 30 50 100 300"])
    plan_path = output / "drawing-pages.json"
    write_json(plan_path, [page.model_dump(mode="json") for page in pages])
    artifacts.append(plan_path)
    manifest = {
        "schema_version": 1,
        "profile": "dxf_pdf_v1",
        "candidate_id": output.parent.name + "/" + output.name,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "fixture_sha256": sha256_file(fixture),
        "template": {
            "manifest_sha256": sha256_file(template_dir / "manifest.json"),
            "layout_sha256": template["layout_sha256"],
            "fonts_sha256": template["fonts_sha256"],
            "template_dxf_sha256": template["template_sha256"],
        },
        "font": glyphs,
        "pages": page_reports,
        "artifact_hashes": {relative(path): sha256_file(path) for path in artifacts},
        "approval_invalidated_by_regeneration": True,
    }
    write_json(output / "candidate-manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
