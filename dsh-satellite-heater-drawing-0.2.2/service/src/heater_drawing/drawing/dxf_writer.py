"""Editable R2018 DXF writer driven by C02 DrawingPage plans."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING
import ezdxf
from ezdxf.math import Matrix44

from heater_drawing.domain.models import DrawingPage, Revision, validate_revision_hash
from .profile import (
    CONTROLLED_DIMSTYLE_VALUES,
    DXF_PDF_PROFILE,
    dimension_overrides,
    dimension_style_values,
    output_template,
)

if TYPE_CHECKING:
    from .layout import PagePlan

APPID = "HEATER_DRAWING"
ALLOWED_MODELSPACE_TYPES = {"LINE", "LWPOLYLINE", "TEXT", "MTEXT", "DIMENSION"}
DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parents[4] / "templates/heater-a4-v1/template.dxf"


def _xy(point) -> tuple[float, float]:
    return float(point.x), float(point.y)


def _tag(entity, *values: str) -> None:
    entity.set_xdata(APPID, [(1000, value) for value in values])


def _add_layers(doc, layout: dict) -> None:
    for item in layout["layers"]:
        if item["name"] not in doc.layers:
            doc.layers.add(item["name"], color=item["aci"], lineweight=item["lineweight"])


def _add_text_style(doc, fonts: dict) -> None:
    name = fonts["dimension_text_style"]
    if name not in doc.styles:
        doc.styles.add(name, font=fonts.get("dimension_cad_font_file", fonts["render_cad_style_font_file"]))
    style = doc.styles.get(name)
    style.dxf.font = fonts.get("dimension_cad_font_file", fonts["render_cad_style_font_file"])
    style.dxf.width = fonts.get("dimension_style_width_factor", 1.0)


def technical_lines(page: DrawingPage, *, sample: bool = False) -> list[str]:
    values = page.fields
    lines = [
        f"1. 电阻值：R={values.resistance_ohm}Ω±{values.tolerance_ohm}Ω；",
        "2. 单回路；",
        "3. 康铜箔BMn40－1.5，GB/T6145-2010；",
        "4. 聚酰亚胺薄膜HF，GB/T13542.6-2006；",
        "5. 导线 Q/YC97A-2011，导线长度均为300mm；",
        "6. 导热线条的走向按工艺最佳方案，",
        "   但导线的引出方向按图所示；",
        "7. 加热片尺寸以图中标注为准；",
        f"8. 数量：{values.quantity_text}。",
    ]
    if sample:
        lines[5] += lines.pop(6).strip()
        return [line.replace(". ", ".", 1) for line in lines]
    return lines


def expected_text_records(layout: dict, page: DrawingPage | None) -> list[dict]:
    records: list[dict] = []
    for index, item in enumerate(layout["fixed_text"]):
        records.append({"kind": "fixed", "id": str(index), **item})
    for name, anchor in layout["field_anchors_mm"].items():
        if page is None:
            value = f"<{name}>"
        elif name == "scale":
            value = page.scale.label
        else:
            value = str(getattr(page.fields, name))
        records.append({"kind": "field", "id": name, **anchor, "text": value})
    if page is not None:
        records.append({
            "kind": "technical",
            "id": "0",
            **layout["technical_text"],
            "text": "技术要求\n" + "\n".join(technical_lines(
                page, sample=layout["technical_text"].get("line_policy") == "sample_original_eight_v1",
            )),
        })
    else:
        records.append({"kind": "technical", "id": "0", **layout["technical_text"]})
    return records


def _add_heater(msp, layout: dict, page: DrawingPage, offset_x: float, fonts: dict) -> None:
    rectangle = page.geometry_mm.rectangle
    left, bottom = _xy(rectangle.origin)
    width = float(rectangle.width_mm)
    length = float(rectangle.length_mm)
    right, top = left + width, bottom + length
    points = [(left + offset_x, bottom), (right + offset_x, bottom),
              (right + offset_x, top), (left + offset_x, top)]
    entity = msp.add_lwpolyline(points, close=True, dxfattribs={"layer": "HEATER"})
    _tag(entity, page.row_id, "heater", page.code)
    for index, segment in enumerate(page.geometry_mm.lead_segments):
        start, end = _xy(segment.start), _xy(segment.end)
        lead = msp.add_line((start[0] + offset_x, start[1]), (end[0] + offset_x, end[1]),
                            dxfattribs={"layer": "HEATER_LEAD"})
        _tag(lead, page.row_id, "lead", str(index))

    factor = float(page.scale.denominator)
    placement_profile = layout["dimension_placement_paper_mm"]
    placement = placement_profile.get("sample_overrides", {}).get(
        page.code, placement_profile["fallback"]
    )
    width_dim_offset = float(placement["width_offset"]) * factor
    length_dim_offset = float(placement["length_offset"]) * factor
    cx, cy = (left + right) / 2 + offset_x, (bottom + top) / 2
    width_dim = msp.add_linear_dim(
        base=(cx, bottom - width_dim_offset), p1=(left + offset_x, bottom), p2=(right + offset_x, bottom),
        angle=0, dimstyle="HEATER_DIM",
        override={"dimscale": factor, **dimension_overrides(fonts, page.code)},
        dxfattribs={"layer": "DIMENSION"},
    )
    width_dim.dimension.dxf.text = "<>"
    _tag(width_dim.dimension, page.row_id, "dimension", "width")
    width_dim.render()
    requested_side = placement["length_side"]
    right_side = (
        page.fields.lead_side.value == "long" and width != length
        if requested_side == "auto"
        else requested_side == "right"
    )
    base_x = right + offset_x + length_dim_offset if right_side else left + offset_x - length_dim_offset
    dim_p1_x = right + offset_x if right_side else left + offset_x
    length_dim = msp.add_linear_dim(
        base=(base_x, cy), p1=(dim_p1_x, bottom), p2=(dim_p1_x, top), angle=90,
        dimstyle="HEATER_DIM",
        override={"dimscale": factor, **dimension_overrides(fonts, page.code)},
        dxfattribs={"layer": "DIMENSION"},
    )
    length_dim.dimension.dxf.text = "<>"
    _tag(length_dim.dimension, page.row_id, "dimension", "length")
    length_dim.render()


def _xdata(entity) -> tuple[str, ...]:
    try:
        return tuple(
            str(value)
            for code, value in entity.get_xdata(APPID)
            if code == 1000
        )
    except ezdxf.DXFValueError:
        return ()


def _configure_doc(layout: dict, fonts: dict, template_path: Path | None = None):
    source = (template_path or DEFAULT_TEMPLATE_PATH).resolve()
    doc = ezdxf.readfile(source)
    doc.header["$INSUNITS"] = DXF_PDF_PROFILE.insunits
    doc.header["$MEASUREMENT"] = 1
    if APPID not in doc.appids:
        doc.appids.add(APPID)
    _add_layers(doc, layout)
    _add_text_style(doc, fonts)
    if "HEATER_DIM" not in doc.dimstyles:
        doc.dimstyles.new("HEATER_DIM")
    dimension_style = doc.dimstyles.get(fonts["dimension_style_name"])
    dimension_style.dxf.dimtxsty = fonts["dimension_text_style"]
    for name, value in dimension_style_values(fonts).items():
        setattr(dimension_style.dxf, name, value)
    return doc


def _template_text_value(record: dict, page: DrawingPage) -> str:
    if record["kind"] == "fixed":
        return record["text"]
    if record["kind"] == "technical":
        return "技术要求\n" + "\n".join(technical_lines(
            page, sample=record.get("line_policy") == "sample_original_eight_v1",
        ))
    if record["id"] == "scale":
        return page.scale.label
    return str(getattr(page.fields, record["id"]))


def _escape_mtext_content(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def expected_mtext_content(record: dict, page: DrawingPage) -> str:
    """Build controlled MTEXT without discarding native paragraph formatting."""
    policy = record.get("content_policy")
    if policy == "preserve_source_raw_v1":
        return str(record["raw_text"])
    if policy == "preserve_source_format_replace_placeholder_v1":
        raw = str(record["raw_text"])
        placeholder = str(record["placeholder"])
        if raw.count(placeholder) != 1:
            raise ValueError(f"MTEXT placeholder is not unique in source content: {placeholder!r}")
        return raw.replace(
            placeholder,
            _escape_mtext_content(_template_text_value(record, page)),
            1,
        )
    if policy == "controlled_unicode_paragraphs_v1":
        lines = ["技术要求", *technical_lines(
            page, sample=record.get("line_policy") == "sample_original_eight_v1",
        )]
        return "\\P".join(_escape_mtext_content(line) for line in lines)
    raise ValueError(
        f"missing or unsupported MTEXT content policy: {record['kind']}/{record['id']}"
    )


def _add_native_template(
    msp,
    source_entities: list,
    page: DrawingPage,
    factor: float,
    offset_x: float,
    layout: dict,
) -> None:
    records = {
        (record["kind"], record["id"]): record
        for record in expected_text_records(layout, page)
    }
    expanded = list(source_entities)
    for source in source_entities:
        identity = _xdata(source)
        if len(identity) != 3 or identity[1] != "fixed":
            continue
        for record in records.values():
            if record.get("native_source_fixed_id") == identity[2]:
                glyph = source.copy()
                glyph.dxf.insert = (*record["point_mm"], 0.0)
                glyph.dxf.align_point = glyph.dxf.insert
                _tag(glyph, "template", "fixed", record["id"])
                expanded.append(glyph)
    for source in expanded:
        entity = source
        msp.add_entity(entity)
        if factor != 1.0:
            entity.transform(Matrix44.scale(factor))
        if offset_x:
            entity.transform(Matrix44.translate(offset_x, 0.0, 0.0))
        identity = _xdata(entity)
        if len(identity) != 3 or identity[0] != "template":
            continue
        if identity[1] == "frame-line":
            continue
        key = (identity[1], identity[2])
        if key not in records:
            raise ValueError(f"unmapped controlled template identity: {identity}")
        record = records[key]
        value = _template_text_value(record, page)
        if entity.dxftype() == "MTEXT":
            entity.text = expected_mtext_content(record, page)
            if record["kind"] == "technical":
                # The source template remains immutable; only the approved block moves.
                entity.dxf.insert = (
                    offset_x + record["point_mm"][0] * factor,
                    record["point_mm"][1] * factor,
                    0.0,
                )
        elif entity.dxftype() == "TEXT":
            entity.dxf.text = value
        else:
            raise ValueError(f"controlled text identity on {entity.dxftype()}")
        _tag(entity, page.row_id, record["kind"], record["id"])


def _native_source_entity_sets(doc, count: int) -> list[list]:
    msp = doc.modelspace()
    entities = list(msp)
    copies = [[entity.copy() for entity in entities] for _ in range(count)]
    for entity in entities:
        msp.delete_entity(entity)
    return copies


def _add_paper(doc, page: DrawingPage, offset_x: float) -> None:
    factor = float(page.scale.denominator)
    paper = doc.layouts.new(page.placement.layout_name)
    paper.page_setup(size=(210, 297), margins=(0, 0, 0, 0), units="mm")
    viewport = paper.add_viewport(center=(105, 148.5), size=(210, 297),
                                  view_center_point=(offset_x + 105 * factor, 148.5 * factor),
                                  view_height=297 * factor, dxfattribs={"status": 2, "layer": "0"})
    # ezdxf creates the paper's main viewport on undeclared VIEWPORTS by default.
    # Keep both viewports on an existing layer so native DWG structural audit passes.
    for paper_viewport in paper.query("VIEWPORT"):
        paper_viewport.dxf.layer = "0"
    _tag(viewport, page.row_id, "viewport")
    if "Layout1" in doc.layout_names():
        doc.layouts.delete("Layout1")


def write_page_dxf(
    path: Path,
    page: DrawingPage,
    layout: dict,
    fonts: dict,
    *,
    template_path: Path | None = None,
) -> None:
    """Write one diagnostic DXF; this does not perform the formal export gate."""

    doc = _configure_doc(layout, fonts, template_path)
    source_entities = _native_source_entity_sets(doc, 1)[0]
    factor = float(page.scale.denominator)
    _add_native_template(doc.modelspace(), source_entities, page, factor, 0.0, layout)
    _add_heater(doc.modelspace(), layout, page, 0.0, fonts)
    _add_paper(doc, page, 0.0)
    if "A4_TEMPLATE" in doc.layout_names():
        doc.layouts.delete("A4_TEMPLATE")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


def write_combined_dxf(
    path: Path,
    pages: list[DrawingPage],
    layout: dict,
    fonts: dict,
    *,
    template_path: Path | None = None,
) -> None:
    """Write diagnostic pages; callers needing a formal artifact must use export_planned_dxf."""

    if not pages:
        raise ValueError("formal DXF export requires at least one planned page")
    doc = _configure_doc(layout, fonts, template_path)
    source_entity_sets = _native_source_entity_sets(doc, len(pages))
    for page, source_entities in zip(pages, source_entity_sets, strict=True):
        if not all(
            check.passed
            for check in (
                page.checks.bounds,
                page.checks.collisions,
                page.checks.glyph_coverage,
            )
        ):
            raise ValueError(f"page has failed preflight checks: {page.row_id}")
        offset = float(page.placement.model_origin_mm.x)
        factor = float(page.scale.denominator)
        _add_native_template(doc.modelspace(), source_entities, page, factor, offset, layout)
        _add_heater(doc.modelspace(), layout, page, offset, fonts)
        _add_paper(doc, page, offset)
    if "A4_TEMPLATE" in doc.layout_names():
        doc.layouts.delete("A4_TEMPLATE")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


def export_planned_dxf(
    path: Path,
    plan: PagePlan,
    revision: Revision,
    template: dict,
) -> None:
    """Replan, read back an isolated candidate, then atomically publish a formal DXF."""

    from .layout import plan_pages
    from .readback import inspect_dxf
    from .template import load_template

    revision = validate_revision_hash(revision)
    template_dir = Path(template["directory"]).resolve()
    controlled = output_template(load_template(template_dir), revision.output_profile)
    fresh = plan_pages(revision, controlled)
    if not fresh.exportable:
        raise ValueError(
            "formal DXF export is forbidden while issues or scale proposals remain"
        )
    if plan != fresh:
        raise ValueError("formal DXF export plan is stale or does not match the revision")
    if (
        fresh.revision_hash != revision.revision_hash
        or fresh.template_hash != revision.template_hash
        or fresh.expected_row_ids != tuple(revision.expected_row_ids)
        or tuple(page.row_id for page in fresh.pages) != tuple(revision.expected_row_ids)
    ):
        raise ValueError("formal DXF export bindings or expected page collection are invalid")

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{path.name}-candidate-", dir=path.parent) as value:
        candidate = Path(value) / path.name
        write_combined_dxf(
            candidate,
            list(fresh.pages),
            controlled["layout"],
            controlled["fonts"],
            template_path=controlled["directory"] / "template.dxf",
        )
        inspect_dxf(
            candidate,
            list(fresh.pages),
            controlled["layout"],
            controlled["fonts"],
        )
        final_template = load_template(template_dir)
        if any(
            final_template[key] != controlled[key]
            for key in ("layout_sha256", "fonts_sha256", "template_sha256")
        ):
            raise ValueError("controlled template changed during formal DXF generation")
        os.replace(candidate, path)


def write_template_dxf(path: Path, layout: dict, fonts: dict) -> None:
    raise RuntimeError(
        "native template refresh requires scripts/refresh_native_template.py "
        "and the hash-bound one-time conversion evidence"
    )
