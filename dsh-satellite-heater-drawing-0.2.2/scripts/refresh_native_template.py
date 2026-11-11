#!/usr/bin/env python3
"""Normalize the authorized one-time DWG conversion into the controlled template."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import ezdxf
from ezdxf.math import Matrix44

from heater_drawing.drawing.text_metrics import aligned_box_mm

ezdxf.options.write_fixed_meta_data_for_testing = True


ROOT = Path(__file__).resolve().parents[1]
APPID = "HEATER_DRAWING"
DYNAMIC_LAYERS = (
    {"name": "HEATER", "aci": 7, "lineweight": 25, "purpose": "true-size four-corner heater outline"},
    {"name": "HEATER_LEAD", "aci": 7, "lineweight": 18, "purpose": "two lead indication lines"},
    {"name": "DIMENSION", "aci": 7, "lineweight": 18, "purpose": "native width and length dimensions"},
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tag(entity, *values: str) -> None:
    entity.set_xdata(APPID, [(1000, value) for value in values])


def _plain_text(entity) -> str:
    return entity.plain_text() if entity.dxftype() == "MTEXT" else entity.dxf.text


def _point(entity) -> list[float]:
    if entity.dxftype() == "TEXT" and (
        int(entity.dxf.get("halign", 0)) or int(entity.dxf.get("valign", 0))
    ):
        value = entity.dxf.align_point
    else:
        value = entity.dxf.insert
    return [round(float(value.x), 12), round(float(value.y), 12)]


def _text_record(entity) -> dict:
    record = {
        "text": _plain_text(entity),
        "entity_type": entity.dxftype(),
        "point_mm": _point(entity),
        "height_mm": float(
            entity.dxf.char_height if entity.dxftype() == "MTEXT" else entity.dxf.height
        ),
        "style": str(entity.dxf.style),
        "rotation": float(entity.dxf.get("rotation", 0.0)),
    }
    if entity.dxftype() == "MTEXT":
        record.update(
            raw_text=str(entity.text),
            attachment_point=int(entity.dxf.get("attachment_point", 1)),
            flow_direction=int(entity.dxf.get("flow_direction", 1)),
            width_mm=float(entity.dxf.get("width", 0.0)),
            line_spacing_factor=float(entity.dxf.get("line_spacing_factor", 1.0)),
            line_spacing_style=int(entity.dxf.get("line_spacing_style", 1)),
        )
    else:
        record.update(
            halign=int(entity.dxf.get("halign", 0)),
            valign=int(entity.dxf.get("valign", 0)),
            width_factor=float(entity.dxf.get("width", 1.0)),
        )
    return record


def _mtext_cell_bounds(entity, frame_lines: list[list]) -> list[float]:
    insert_x = float(entity.dxf.insert.x)
    insert_y = float(entity.dxf.insert.y)
    width = float(entity.dxf.get("width", 0.0))
    attachment = int(entity.dxf.get("attachment_point", 1))
    horizontal = attachment in {1, 4, 7}
    centered = attachment in {2, 5, 8}
    if horizontal:
        left = insert_x
    elif centered:
        left = insert_x - width / 2.0
    else:
        left = insert_x - width
    right = left + width
    midpoint = (left + right) / 2.0
    y_values = sorted(
        {
            float(line[1])
            for line in frame_lines
            if abs(float(line[1]) - float(line[3])) <= 1e-9
            and min(float(line[0]), float(line[2])) - 1e-9 <= midpoint
            <= max(float(line[0]), float(line[2])) + 1e-9
        }
    )
    below = [value for value in y_values if value < insert_y - 1e-9]
    above = [value for value in y_values if value > insert_y + 1e-9]
    if not below or not above:
        raise ValueError(f"cannot derive native MTEXT cell bounds at {insert_x}, {insert_y}")
    return [left, max(below), right, min(above)]


def _text_alignment(entity) -> str:
    halign = int(entity.dxf.get("halign", 0))
    valign = int(entity.dxf.get("valign", 0))
    return {
        (0, 0): "LEFT",
        (1, 0): "CENTER",
        (2, 0): "RIGHT",
        (0, 1): "BOTTOM_LEFT",
        (1, 1): "BOTTOM_CENTER",
        (2, 1): "BOTTOM_RIGHT",
        (0, 2): "MIDDLE_LEFT",
        (1, 2): "MIDDLE_CENTER",
        (2, 2): "MIDDLE_RIGHT",
        (0, 3): "TOP_LEFT",
        (1, 3): "TOP_CENTER",
        (2, 3): "TOP_RIGHT",
    }.get((halign, valign), "LEFT")


def _frame_crossing_indexes(
    box: tuple[float, float, float, float], frame_lines: list[list]
) -> list[int]:
    left, bottom, right, top = box
    clearance = 0.01
    indexes = []
    for index, (x1, y1, x2, y2, *_) in enumerate(frame_lines):
        if abs(float(x1) - float(x2)) <= 1e-6:
            crosses = (
                left + clearance < float(x1) < right - clearance
                and max(bottom, min(float(y1), float(y2)))
                < min(top, max(float(y1), float(y2))) - clearance
            )
        else:
            crosses = (
                bottom + clearance < float(y1) < top - clearance
                and max(left, min(float(x1), float(x2)))
                < min(right, max(float(x1), float(x2))) - clearance
            )
        if crosses:
            indexes.append(index)
    return indexes


def refresh(source: Path, template_dir: Path) -> None:
    layout_path = template_dir / "layout.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    font_profile = json.loads(
        (template_dir / "fonts.json").read_text(encoding="utf-8")
    )
    source_profile = layout["source_template"]
    if _sha256(source) != source_profile["sha256"]:
        raise ValueError("authorized source DXF hash mismatch")

    doc = ezdxf.readfile(source)
    if doc.dxfversion != "AC1032" or int(doc.header.get("$INSUNITS", 0)) != 4:
        raise ValueError("source DXF profile mismatch")
    msp = doc.modelspace()
    if len(msp) != source_profile["modelspace_entity_count"]:
        raise ValueError("source modelspace entity count mismatch")
    if len(msp.query("LINE")) != source_profile["line_count"]:
        raise ValueError("source line count mismatch")
    if len(msp.query("TEXT MTEXT")) != source_profile["text_count"]:
        raise ValueError("source text count mismatch")

    source_x, source_y = source_profile["model_origin_mm"]
    paper_x, paper_y = source_profile["paper_origin_mm"]
    transform = Matrix44.translate(paper_x - source_x, paper_y - source_y, 0.0)
    for entity in msp:
        entity.transform(transform)

    if APPID not in doc.appids:
        doc.appids.add(APPID)
    for index, entity in enumerate(msp.query("LINE")):
        _tag(entity, "template", "frame-line", str(index))

    frame_lines = []
    for entity in msp.query("LINE"):
        frame_lines.append(
            [
                round(float(entity.dxf.start.x), 12),
                round(float(entity.dxf.start.y), 12),
                round(float(entity.dxf.end.x), 12),
                round(float(entity.dxf.end.y), 12),
                str(entity.dxf.layer),
                int(entity.dxf.get("color", 256)),
                entity.dxf.get("true_color", None),
                str(entity.dxf.get("linetype", "BYLAYER")),
            ]
        )

    placeholders = source_profile["dynamic_placeholders"]
    fixed_text: list[dict] = []
    field_anchors: dict[str, dict] = {}
    technical_text = None
    for entity in msp.query("TEXT MTEXT"):
        value = _plain_text(entity)
        record = _text_record(entity)
        if value in placeholders:
            field = placeholders[value]
            record["placeholder"] = value
            record["content_policy"] = "preserve_source_format_replace_placeholder_v1"
            record["bounds_mm"] = _mtext_cell_bounds(entity, frame_lines)
            field_anchors[field] = record
            _tag(entity, "template", "field", field)
        elif value.startswith("技术要求\n"):
            record["content_policy"] = "controlled_unicode_paragraphs_v1"
            record["bounds_mm"] = [
                float(layout["technical_text_bbox_mm"][name])
                for name in ("left", "bottom", "right", "top")
            ]
            record["bounds_tolerance_mm"] = 0.25
            technical_text = record
            _tag(entity, "template", "technical", "0")
        else:
            if entity.dxftype() == "MTEXT":
                record["content_policy"] = "preserve_source_raw_v1"
                record["allowed_frame_crossings"] = []
            else:
                glyph_box = aligned_box_mm(
                    record["text"],
                    tuple(record["point_mm"]),
                    record["height_mm"],
                    font_profile,
                    _text_alignment(entity),
                    record["width_factor"],
                    record["rotation"],
                )
                record["allowed_frame_crossings"] = _frame_crossing_indexes(
                    glyph_box, frame_lines
                )
            index = len(fixed_text)
            fixed_text.append(record)
            _tag(entity, "template", "fixed", str(index))
    if set(field_anchors) != set(placeholders.values()) or technical_text is None:
        raise ValueError("source template placeholder mapping is incomplete")

    layers = []
    for layer in doc.layers:
        layers.append(
            {
                "name": str(layer.dxf.name),
                "aci": int(layer.dxf.color),
                "true_color": layer.dxf.get("true_color", None),
                "linetype": str(layer.dxf.get("linetype", "Continuous")),
                "lineweight": int(layer.dxf.get("lineweight", -3)),
                "plot": int(layer.dxf.get("plot", 1)),
                "purpose": "preserved original DWG layer",
            }
        )
    for item in DYNAMIC_LAYERS:
        if item["name"] not in doc.layers:
            doc.layers.add(item["name"], color=item["aci"], lineweight=item["lineweight"])
        layers.append(dict(item, true_color=None, linetype="Continuous", plot=1))

    if "HEATER_CJK" not in doc.styles:
        doc.styles.add("HEATER_CJK", font="NotoSansCJKsc-Regular.otf")
    if "HEATER_DIM" not in doc.dimstyles:
        doc.dimstyles.new("HEATER_DIM")
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    paper_names = [name for name in doc.layout_names() if name != "Model"]
    doc.layouts.rename(paper_names[0], "A4_TEMPLATE")
    paper = doc.layouts.get("A4_TEMPLATE")
    for name in paper_names[1:]:
        doc.layouts.delete(name)
    paper.page_setup(size=(210, 297), margins=(0, 0, 0, 0), units="mm")

    layout["layers"] = layers
    layout["frame_lines_mm"] = frame_lines
    layout["fixed_text"] = fixed_text
    layout["field_anchors_mm"] = field_anchors
    layout["technical_text"] = technical_text
    layout_path.write_text(
        json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    doc.saveas(template_dir / "template.dxf")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "docs/evidence/B02-fix-12/original-template/CAD模板-r2018.dxf",
    )
    parser.add_argument(
        "--template-dir", type=Path, default=ROOT / "templates/heater-a4-v1"
    )
    args = parser.parse_args()
    refresh(args.source.resolve(), args.template_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
