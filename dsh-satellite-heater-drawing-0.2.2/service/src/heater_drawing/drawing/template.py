"""Load and validate the controlled A4 template description."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import ezdxf


class TemplateError(ValueError):
    pass


REQUIRED_LAYOUT_KEYS = {
    "paper_mm",
    "outer_border_mm",
    "drawing_area_mm",
    "technical_text_bbox_mm",
    "title_block_bbox_mm",
    "forbidden_zones_mm",
    "field_anchors_mm",
    "lead_parameters_paper_mm",
    "dimension_placement_paper_mm",
    "standard_scale_denominators",
    "layers",
    "fixed_text",
    "technical_text",
    "fixed_text_version",
    "frame_lines_mm",
    "source_template",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_template(template_dir: Path) -> dict[str, Any]:
    template_dir = template_dir.resolve()
    layout_path = template_dir / "layout.json"
    fonts_path = template_dir / "fonts.json"
    manifest_path = template_dir / "manifest.json"
    template_path = template_dir / "template.dxf"
    for path in (layout_path, fonts_path, manifest_path, template_path):
        if not path.is_file():
            raise TemplateError(f"missing controlled template file: {path.name}")
    try:
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        fonts = json.loads(fonts_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TemplateError(f"invalid template JSON: {exc}") from exc
    missing = sorted(REQUIRED_LAYOUT_KEYS - set(layout))
    if missing:
        raise TemplateError(f"layout lacks keys: {', '.join(missing)}")
    if layout.get("schema_version") != 1 or manifest.get("schema_version") != 1:
        raise TemplateError("unsupported template schema version")
    if layout["paper_mm"] != {"width": 210.0, "height": 297.0}:
        raise TemplateError("template paper must be A4 portrait in millimetres")
    if fonts.get("cad_text_mode") != "editable_text":
        raise TemplateError("CAD text must remain editable")
    expected = manifest.get("controlled_files", {})
    for name in ("layout.json", "fonts.json", "template.dxf"):
        actual = sha256_file(template_dir / name)
        if expected.get(name) != actual:
            raise TemplateError(f"controlled hash mismatch: {name}")
    try:
        document = ezdxf.readfile(template_path)
    except (OSError, ezdxf.DXFError) as exc:
        raise TemplateError(f"invalid controlled template.dxf: {exc}") from exc
    if document.dxfversion != "AC1032" or int(document.header.get("$INSUNITS", 0)) != 4:
        raise TemplateError("controlled template DXF profile mismatch")
    if "A4_TEMPLATE" not in document.layout_names() or "Layout1" in document.layout_names():
        raise TemplateError("controlled template layouts are invalid")
    expected_layers = {item["name"] for item in layout["layers"]}
    if not expected_layers.issubset({layer.dxf.name for layer in document.layers}):
        raise TemplateError("controlled template layers are incomplete")
    if len(list(document.modelspace().query("LINE"))) != len(layout["frame_lines_mm"]):
        raise TemplateError("controlled native template line structure mismatch")
    if len(list(document.modelspace().query("TEXT MTEXT"))) != len(layout["fixed_text"]) + len(layout["field_anchors_mm"]) + 1:
        raise TemplateError("controlled template text structure mismatch")
    records = [
        *layout["fixed_text"],
        *layout["field_anchors_mm"].values(),
        layout["technical_text"],
    ]
    required_mtext = {
        "raw_text",
        "attachment_point",
        "flow_direction",
        "width_mm",
        "line_spacing_factor",
        "line_spacing_style",
        "content_policy",
    }
    for record in records:
        if record["entity_type"] == "MTEXT" and not required_mtext.issubset(record):
            raise TemplateError("controlled MTEXT source-format contract is incomplete")
    if any("allowed_frame_crossings" not in record for record in layout["fixed_text"]):
        raise TemplateError("fixed-text frame-crossing baseline is incomplete")
    return {
        "directory": template_dir,
        "layout": layout,
        "fonts": fonts,
        "manifest": manifest,
        "layout_sha256": sha256_file(layout_path),
        "fonts_sha256": sha256_file(fonts_path),
        "template_sha256": sha256_file(template_path),
    }


def write_manifest(template_dir: Path) -> Path:
    template_dir = template_dir.resolve()
    template_path = template_dir / "template.dxf"
    controlled = {
        name: sha256_file(template_dir / name)
        for name in ("layout.json", "fonts.json")
    }
    if template_path.is_file():
        controlled["template.dxf"] = sha256_file(template_path)
    payload = {
        "schema_version": 1,
        "template_id": "heater-a4-v1",
        "version": "1.4.0-development-baseline",
        "status": "development_baseline_delivery_approval_pending",
        "source_method": "native entities preserved from the hash-bound one-time ODA R2018 DXF conversion of the original DWG; translated to controlled paper coordinates without geometric scaling",
        "source_hashes": {
            "fixtures/case/CAD模板.dwg": "7c917bb7805aefd8ce327ca7f1e6912c2fcfabcb68ee91569f71503638c82676",
            "fixtures/case/加热器图纸.pdf": "c38953be0adaac425e1d6a7b9dcdef2fe9a4332f49bea1811a94a69e42aaa912",
        },
        "controlled_files": controlled,
        "approval_evidence": "docs/evidence/B02-development-baseline/human-approval.json",
    }
    path = template_dir / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
