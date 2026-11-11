"""Strict semantic DXF readback for the controlled B02 format."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import bbox
from ezdxf.addons import MTextExplode, text2path
from ezdxf.math import Vec3
from ezdxf.path import bbox as path_bbox
from ezdxf.tools.text import MTextParser

from heater_drawing.domain.models import DrawingPage
from .dxf_writer import (
    ALLOWED_MODELSPACE_TYPES,
    expected_mtext_content,
    expected_text_records,
)
from .display_profile import (
    controlled_dimension_linetype_error,
    controlled_dimension_linetype_signature,
    controlled_entity_display_error,
    controlled_entity_display_signature,
    controlled_layer_error,
    controlled_layer_signature,
)
from .fonts import check_glyph_coverage
from .profile import (
    CONTROLLED_DIMENSION_OVERRIDES,
    CONTROLLED_DIMENSION_LINETYPE_FIELDS,
    CONTROLLED_DIMSTYLE_VALUES,
    DXF_PDF_PROFILE,
    dimension_overrides as profile_dimension_overrides,
    dimension_style_values,
)
from .text_metrics import aligned_box_mm, box_inside, font_constants, locked_font, locked_font_path


class ReadbackError(ValueError):
    pass


def _xdata(entity) -> tuple[str, ...]:
    try:
        return tuple(str(value) for code, value in entity.get_xdata("HEATER_DRAWING") if code == 1000)
    except ezdxf.DXFValueError:
        return ()


def _close(a: float, b: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(float(a), float(b), abs_tol=tolerance)


def _controlled_dimension_text(value: float) -> str:
    """Format a measurement from the locked DIMSTYLE, independently of its cache."""
    rounding = float(CONTROLLED_DIMSTYLE_VALUES["dimrnd"])
    value = round(value) if rounding == 0.0 else round(value / rounding) * rounding
    decimal_places = int(CONTROLLED_DIMSTYLE_VALUES["dimdec"])
    text = f"{value:.{decimal_places}f}"

    suppress_zeros = int(CONTROLLED_DIMSTYLE_VALUES["dimzin"])
    if float(text) == 0.0:
        text = "0"
    else:
        sign = text[0] if text[0] in "-+" else ""
        unsigned = text[1:] if sign else text
        if suppress_zeros & 4:
            unsigned = unsigned.lstrip("0")
        if suppress_zeros & 8 and "." in unsigned:
            unsigned = unsigned.rstrip("0").rstrip(".")
        text = sign + unsigned

    separator = chr(int(CONTROLLED_DIMSTYLE_VALUES["dimdsep"]))
    return text.replace(".", separator)


def _point(value) -> tuple[float, float]:
    return float(value.x), float(value.y)


def _require_point(actual, expected: tuple[float, float], label: str) -> None:
    if not (_close(actual.x, expected[0]) and _close(actual.y, expected[1])):
        raise ReadbackError(f"{label} drift: ({actual.x}, {actual.y})")


def _angle_close(actual: float, expected: float) -> bool:
    return _close((float(actual) - float(expected)) % 360.0, 0.0) or _close(
        (float(expected) - float(actual)) % 360.0, 0.0
    )


def _one(entities, identity: tuple[str, ...], label: str):
    matches = [entity for entity in entities if _xdata(entity) == identity]
    if len(matches) != 1:
        raise ReadbackError(f"{label} identity/handle mapping mismatch: {identity}")
    return matches[0]


def _solid_count(entities) -> int:
    count = 0
    for entity in entities:
        if entity.dxftype() == "SOLID":
            count += 1
        elif entity.dxftype() == "INSERT":
            count += _solid_count(entity.virtual_entities())
    return count


def _paper_point(value, offset_x: float, factor: float) -> list[float]:
    return [
        round((float(value.x) - offset_x) / factor, 9),
        round(float(value.y) / factor, 9),
        round(float(getattr(value, "z", 0.0)) / factor, 9),
    ]


def _paper_vector(value, factor: float) -> list[float]:
    return [
        round(float(value.x) / factor, 9),
        round(float(value.y) / factor, 9),
        round(float(getattr(value, "z", 0.0)) / factor, 9),
    ]


_CACHE_COMMON_DXF_ATTRIBUTES = {
    "handle", "owner", "layer", "color", "true_color", "transparency",
    "linetype", "ltscale", "lineweight", "invisible", "material_handle",
    "plotstyle_handle", "shadow_mode", "visualstyle_handle", "extrusion", "thickness",
}

_CACHE_KIND_DXF_ATTRIBUTES = {
    "LINE": {"start", "end"},
    "ARC": {"center", "radius", "start_angle", "end_angle"},
    "CIRCLE": {"center", "radius"},
    "LWPOLYLINE": {"elevation", "flags", "const_width", "count"},
    "SOLID": {"vtx0", "vtx1", "vtx2", "vtx3"},
    "MTEXT": {
        "text", "insert", "char_height", "width", "attachment_point", "flow_direction",
        "style", "text_direction", "rect_width", "rect_height", "rotation",
        "line_spacing_style", "line_spacing_factor", "box_fill_scale", "bg_fill",
        "bg_fill_color", "bg_fill_true_color", "bg_fill_transparency", "column_type",
        "column_auto_height", "column_count", "column_width", "column_gutter",
        "column_heights",
    },
    "TEXT": {
        "text", "insert", "align_point", "height", "width", "rotation", "style",
        "text_generation_flag", "halign", "valign", "oblique",
    },
    "INSERT": {"name", "insert", "rotation", "xscale", "yscale", "zscale", "attribs_follow"},
}


def _dxf_value(entity, name: str, default: Any) -> Any:
    if not entity.dxf.is_supported(name):
        return default
    return entity.dxf.get(name, default)


def _cache_display_signature(entity, factor: float) -> dict[str, Any]:
    extrusion = _dxf_value(entity, "extrusion", Vec3(0.0, 0.0, 1.0))
    return {
        "true_color": _dxf_value(entity, "true_color", None),
        "transparency": _dxf_value(entity, "transparency", None),
        "ltscale": round(float(_dxf_value(entity, "ltscale", 1.0)), 9),
        "invisible": int(_dxf_value(entity, "invisible", 0)),
        "material_handle": str(_dxf_value(entity, "material_handle", "0")),
        "plotstyle_handle": str(_dxf_value(entity, "plotstyle_handle", "0")),
        "shadow_mode": int(_dxf_value(entity, "shadow_mode", 0)),
        "visualstyle_handle": str(_dxf_value(entity, "visualstyle_handle", "0")),
        "extrusion": _paper_vector(extrusion, 1.0),
        "thickness": round(float(_dxf_value(entity, "thickness", 0.0)) / factor, 9),
    }


def _cache_entity_signature(entity, offset_x: float, factor: float) -> dict[str, Any]:
    kind = entity.dxftype()
    signature: dict[str, Any] = {
        "type": kind,
        "layer": str(entity.dxf.get("layer", "0")),
        "color": int(entity.dxf.get("color", 256)),
        "linetype": str(entity.dxf.get("linetype", "BYLAYER")).upper(),
        "lineweight": int(entity.dxf.get("lineweight", -1)),
        "display": _cache_display_signature(entity, factor),
    }
    if kind == "LINE":
        signature.update(
            start=_paper_point(entity.dxf.start, offset_x, factor),
            end=_paper_point(entity.dxf.end, offset_x, factor),
        )
    elif kind == "ARC":
        signature.update(
            center=_paper_point(entity.dxf.center, offset_x, factor),
            radius=round(float(entity.dxf.radius) / factor, 9),
            start_angle=round(float(entity.dxf.start_angle), 9),
            end_angle=round(float(entity.dxf.end_angle), 9),
        )
    elif kind == "CIRCLE":
        signature.update(
            center=_paper_point(entity.dxf.center, offset_x, factor),
            radius=round(float(entity.dxf.radius) / factor, 9),
        )
    elif kind == "LWPOLYLINE":
        signature.update(
            points=[
                [
                    round((float(x) - offset_x) / factor, 9),
                    round(float(y) / factor, 9),
                    round(float(start_width) / factor, 9),
                    round(float(end_width) / factor, 9),
                    round(float(bulge), 9),
                ]
                for x, y, start_width, end_width, bulge in entity.get_points("xyseb")
            ],
            closed=bool(entity.closed),
            elevation=round(float(_dxf_value(entity, "elevation", 0.0)) / factor, 9),
            const_width=round(float(_dxf_value(entity, "const_width", 0.0)) / factor, 9),
        )
    elif kind == "SOLID":
        signature["vertices"] = [
            _paper_point(entity.dxf.get(name), offset_x, factor)
            for name in ("vtx0", "vtx1", "vtx2", "vtx3")
        ]
    elif kind == "MTEXT":
        signature.update(
            raw_text=str(entity.dxf.text),
            plain_text=entity.plain_text(),
            insert=_paper_point(entity.dxf.insert, offset_x, factor),
            char_height=round(float(entity.dxf.char_height) / factor, 9),
            width=round(float(entity.dxf.get("width", 0.0)) / factor, 9),
            attachment=int(entity.dxf.get("attachment_point", 1)),
            rotation=round(float(entity.get_rotation()), 9),
            # MTEXT may encode the same orientation as a rotation or a direction.
            # Native CAD writes the latter on save; compare the effective direction.
            text_direction=_paper_vector(entity.get_text_direction().normalize(), 1.0),
            style=str(entity.dxf.get("style", "Standard")),
            line_spacing_factor=round(float(entity.dxf.get("line_spacing_factor", 1.0)), 9),
            line_spacing_style=int(entity.dxf.get("line_spacing_style", 1)),
            flow_direction=int(_dxf_value(entity, "flow_direction", 1)),
            background={
                "enabled": int(_dxf_value(entity, "bg_fill", 0)),
                "scale": round(float(_dxf_value(entity, "box_fill_scale", 1.5)), 9),
                "aci": int(_dxf_value(entity, "bg_fill_color", 0)),
                "true_color": _dxf_value(entity, "bg_fill_true_color", None),
                "transparency": _dxf_value(entity, "bg_fill_transparency", None),
            },
        )
    elif kind == "TEXT":
        signature.update(
            text=str(entity.dxf.text),
            insert=_paper_point(entity.dxf.insert, offset_x, factor),
            align_point=_paper_point(entity.dxf.get("align_point", entity.dxf.insert), offset_x, factor),
            height=round(float(entity.dxf.height) / factor, 9),
            width=round(float(entity.dxf.get("width", 1.0)), 9),
            rotation=round(float(entity.dxf.get("rotation", 0.0)), 9),
            style=str(entity.dxf.get("style", "Standard")),
            halign=int(entity.dxf.get("halign", 0)),
            valign=int(entity.dxf.get("valign", 0)),
            oblique=round(float(_dxf_value(entity, "oblique", 0.0)), 9),
            text_generation_flag=int(_dxf_value(entity, "text_generation_flag", 0)),
        )
    elif kind == "INSERT":
        children = [
            _cache_entity_signature(child, offset_x, factor)
            for child in entity.virtual_entities()
            if child.dxftype() != "POINT"
        ]
        signature.update(
            name=str(entity.dxf.name),
            insert=_paper_point(entity.dxf.insert, offset_x, factor),
            rotation=round(float(entity.dxf.get("rotation", 0.0)), 9),
            xscale=round(float(entity.dxf.get("xscale", 1.0)), 9),
            yscale=round(float(entity.dxf.get("yscale", 1.0)), 9),
            zscale=round(float(entity.dxf.get("zscale", 1.0)), 9),
            children=sorted(children, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True)),
        )
    else:
        raise ReadbackError(f"unsupported visible dimension cache entity: {kind}")
    known = _CACHE_COMMON_DXF_ATTRIBUTES | _CACHE_KIND_DXF_ATTRIBUTES[kind]
    signature["unsupported_explicit_attributes"] = sorted(
        set(entity.dxf.all_existing_dxf_attribs()) - known
    )
    return signature


def _dimension_cache_signature(entities, offset_x: float, factor: float) -> list[dict[str, Any]]:
    signatures = [
        _cache_entity_signature(entity, offset_x, factor)
        for entity in entities
        if entity.dxftype() != "POINT"
    ]
    return sorted(signatures, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _expected_dimension_cache_signature(
    *,
    kind: str,
    left: float,
    bottom: float,
    right: float,
    top: float,
    dim_offset: float,
    factor: float,
    offset_x: float,
    long_lead: bool,
    font_profile: dict,
    dimstyle_linetypes: dict[str, Any],
    dimension_overrides: dict[str, Any],
) -> list[dict[str, Any]]:
    document = ezdxf.new(DXF_PDF_PROFILE.dxf_version, setup=True)
    document.layers.add("DIMENSION", color=7)
    document.styles.add(
        font_profile["dimension_text_style"],
        font=font_profile.get("dimension_cad_font_file", font_profile["render_cad_style_font_file"]),
        dxfattribs={"width": font_profile.get("dimension_style_width_factor", 1.0)},
    )
    dimension_style = document.dimstyles.new(font_profile["dimension_style_name"])
    dimension_style.dxf.dimtxsty = font_profile["dimension_text_style"]
    for name, setting in dimension_style_values(font_profile).items():
        setattr(dimension_style.dxf, name, setting)
    for name in CONTROLLED_DIMENSION_LINETYPE_FIELDS:
        setting = dimstyle_linetypes.get(name)
        if setting is not None:
            setattr(dimension_style.dxf, name, setting)
    overrides = {"dimscale": factor, **CONTROLLED_DIMENSION_OVERRIDES}
    overrides.update({name: dimension_overrides[name] for name in CONTROLLED_DIMENSION_OVERRIDES})
    overrides.update(
        {
            name: dimension_overrides[name]
            for name in CONTROLLED_DIMENSION_LINETYPE_FIELDS
            if name in dimension_overrides
        }
    )
    if kind == "width":
        construction = document.modelspace().add_linear_dim(
            base=((left + right) / 2.0, bottom - dim_offset),
            p1=(left, bottom),
            p2=(right, bottom),
            angle=0,
            dimstyle=font_profile["dimension_style_name"],
            override=overrides,
            dxfattribs={"layer": "DIMENSION"},
        )
    else:
        base_x = right + dim_offset if long_lead else left - dim_offset
        point_x = right if long_lead else left
        construction = document.modelspace().add_linear_dim(
            base=(base_x, (bottom + top) / 2.0),
            p1=(point_x, bottom),
            p2=(point_x, top),
            angle=90,
            dimstyle=font_profile["dimension_style_name"],
            override=overrides,
            dxfattribs={"layer": "DIMENSION"},
        )
    construction.dimension.dxf.text = "<>"
    construction.render()
    return _dimension_cache_signature(
        construction.dimension.virtual_entities(), offset_x, factor
    )


def _validate_rectangle(entity, page: DrawingPage, offset_x: float) -> tuple[float, float]:
    if not entity.closed:
        raise ReadbackError(f"heater rectangle is not closed for {page.row_id}")
    vertices = list(entity.get_points("xyb"))
    if len(vertices) != 4 or any(not _close(vertex[2], 0.0) for vertex in vertices):
        raise ReadbackError(f"heater must have exactly four straight corners for {page.row_id}")
    origin = page.geometry_mm.rectangle.origin
    left, bottom = float(origin.x) + offset_x, float(origin.y)
    width, length = float(page.geometry_mm.rectangle.width_mm), float(page.geometry_mm.rectangle.length_mm)
    expected = [(left, bottom), (left + width, bottom), (left + width, bottom + length), (left, bottom + length)]
    actual = [(float(x), float(y)) for x, y, _ in vertices]
    if any(not (_close(a[0], e[0]) and _close(a[1], e[1])) for a, e in zip(actual, expected)):
        raise ReadbackError(f"heater corner/right-angle drift for {page.row_id}")
    for index in range(4):
        a, b, c = actual[index - 1], actual[index], actual[(index + 1) % 4]
        dot = (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1])
        if not _close(dot, 0.0):
            raise ReadbackError(f"heater corner is not a right angle for {page.row_id}")
    return width, length


def _validate_viewport(doc, page: DrawingPage, offset_x: float) -> str:
    if page.placement.layout_name not in doc.layout_names():
        raise ReadbackError(f"missing A4 layout: {page.placement.layout_name}")
    paper = doc.layouts.get(page.placement.layout_name)
    viewport = _one(list(paper.query("VIEWPORT")), (page.row_id, "viewport"), "viewport")
    factor = float(page.scale.denominator)
    _require_point(viewport.dxf.center, (105.0, 148.5), "viewport paper center")
    _require_point(viewport.dxf.view_center_point, (offset_x + 105.0 * factor, 148.5 * factor), "viewport model center")
    if not _close(viewport.dxf.width, 210.0) or not _close(viewport.dxf.height, 297.0):
        raise ReadbackError(f"viewport crop drift for {page.row_id}")
    if not _close(viewport.dxf.view_height, 297.0 * factor):
        raise ReadbackError(f"viewport scale drift for {page.row_id}")
    if not _close(viewport.dxf.get("view_twist_angle", 0.0), 0.0):
        raise ReadbackError(f"viewport twist drift for {page.row_id}")
    if not _close(paper.dxf.paper_width, 210.0) or not _close(paper.dxf.paper_height, 297.0):
        raise ReadbackError(f"paper size drift for {page.row_id}")
    if int(paper.dxf.plot_rotation) != 0 or int(paper.dxf.plot_paper_units) != 1:
        raise ReadbackError(f"paper rotation/unit drift for {page.row_id}")
    if any(not _close(paper.dxf.get(name, 0.0), 0.0) for name in ("left_margin", "right_margin", "top_margin", "bottom_margin")):
        raise ReadbackError(f"paper crop/margin drift for {page.row_id}")
    return viewport.dxf.handle


def _mtext_format_signature(content: str) -> list[dict[str, Any]]:
    signature: list[dict[str, Any]] = []
    for token in MTextParser(content):
        context = token.ctx
        paragraph = context.paragraph
        font = context.font_face
        data = token.data
        if not isinstance(data, (str, int, float, bool, type(None))):
            data = str(data)
        signature.append(
            {
                "type": int(token.type),
                "data": data,
                "cap_height": round(float(context.cap_height), 9),
                "width_factor": round(float(context.width_factor), 9),
                "tracking_factor": round(float(context.char_tracking_factor), 9),
                "oblique": round(float(context.oblique), 9),
                "aci": int(context.aci),
                "rgb": list(context.rgb) if context.rgb is not None else None,
                "line_alignment": int(context.align),
                "underline": bool(context.underline),
                "overline": bool(context.overline),
                "strike_through": bool(context.strike_through),
                "font": {
                    "filename": str(font.filename),
                    "family": str(font.family),
                    "style": str(font.style),
                    "weight": int(font.weight),
                    "width": int(font.width),
                },
                "paragraph": {
                    "indent": round(float(paragraph.indent), 9),
                    "left": round(float(paragraph.left), 9),
                    "right": round(float(paragraph.right), 9),
                    "alignment": int(paragraph.align),
                    "tab_stops": [str(item) for item in paragraph.tab_stops],
                },
            }
        )
    return signature


def _mtext_glyph_box(
    entity,
    doc,
    font_path: Path,
    font_profile: dict,
    factor: float,
    offset_x: float,
    *,
    native_technical: bool = False,
) -> tuple[float, float, float, float]:
    if native_technical and font_profile.get("native_hz_technical_metrics"):
        from .native_text_metrics import measure_hz_mtext
        return measure_hz_mtext(entity, font_profile, factor, offset_x)
    from .pdf_renderer import _locked_ezdxf_font

    render_style = "HEATER_READBACK_NOTO"
    if render_style not in doc.styles:
        style = doc.styles.add(render_style, font=font_path.name)
        style.dxf.width = font_profile["cad_style_width_factor"]
    source = doc.blocks.new_anonymous_block()
    controlled = entity.copy()
    source.add_entity(controlled)
    if controlled.dxf.style == font_profile["cad_style_name"]:
        controlled.dxf.style = render_style
    exploded = doc.blocks.new_anonymous_block()
    with _locked_ezdxf_font(font_path):
        with MTextExplode(exploded, doc=doc) as exploder:
            exploder.explode(controlled, destroy=False)
        paths = [
            path
            for text_entity in exploded.query("TEXT")
            for path in text2path.make_paths_from_entity(text_entity)
        ]
    extent = path_bbox(paths)
    if not extent.has_data:
        raise ReadbackError("MTEXT visible glyph bounds are unavailable")
    return (
        (float(extent.extmin.x) - offset_x) / factor,
        float(extent.extmin.y) / factor,
        (float(extent.extmax.x) - offset_x) / factor,
        float(extent.extmax.y) / factor,
    )


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


def _single_line_mtext_glyph_box(
    entity,
    text: str,
    font_profile: dict,
    factor: float,
    offset_x: float,
) -> tuple[float, float, float, float]:
    alignment = {
        1: "TOP_LEFT",
        2: "TOP_CENTER",
        3: "TOP_RIGHT",
        4: "MIDDLE_LEFT",
        5: "MIDDLE_CENTER",
        6: "MIDDLE_RIGHT",
        7: "BOTTOM_LEFT",
        8: "BOTTOM_CENTER",
        9: "BOTTOM_RIGHT",
    }.get(int(entity.dxf.get("attachment_point", 1)), "TOP_LEFT")
    insert = entity.dxf.insert
    return aligned_box_mm(
        text,
        ((float(insert.x) - offset_x) / factor, float(insert.y) / factor),
        float(entity.dxf.char_height) / factor,
        font_profile,
        alignment,
        font_profile.get("dimension_style_width_factor", 1.0),
        entity.get_rotation(),
    )


def _frame_crossing_indexes(
    box: tuple[float, float, float, float], layout: dict
) -> list[int]:
    left, bottom, right, top = box
    clearance = 0.01
    indexes = []
    for index, (x1, y1, x2, y2, *_) in enumerate(layout["frame_lines_mm"]):
        if _close(x1, x2):
            crosses = (
                left + clearance < x1 < right - clearance
                and max(bottom, min(y1, y2)) < min(top, max(y1, y2)) - clearance
            )
        else:
            crosses = (
                bottom + clearance < y1 < top - clearance
                and max(left, min(x1, x2)) < min(right, max(x1, x2)) - clearance
            )
        if crosses:
            indexes.append(index)
    return indexes


def _validate_texts(
    texts,
    doc,
    layout: dict,
    page: DrawingPage,
    factor: float,
    offset_x: float,
    font_profile: dict,
    font_path: Path,
) -> tuple[dict[str, str], list[dict]]:
    handles: dict[str, str] = {}
    measurements: list[dict] = []
    font_constants(font_profile)
    for record in expected_text_records(layout, page):
        identity = (page.row_id, record["kind"], record["id"])
        entity = _one(texts, identity, "text")
        expected = record["text"]
        actual = entity.dxf.text if entity.dxftype() == "TEXT" else entity.plain_text()
        if actual != expected:
            raise ReadbackError(f"text value drift for {page.row_id}/{record['kind']}/{record['id']}")
        if entity.dxftype() != record["entity_type"]:
            raise ReadbackError(f"editable text entity type drift for {identity}")
        point = record["point_mm"]
        if entity.dxftype() == "MTEXT":
            actual_point = entity.dxf.insert
            height = entity.dxf.char_height
            expected_content = expected_mtext_content(record, page)
            if (
                int(entity.dxf.get("attachment_point", 1)) != record["attachment_point"]
                or int(entity.dxf.get("flow_direction", 1)) != record["flow_direction"]
                or not _close(entity.dxf.get("width", 0.0), record["width_mm"] * factor)
                or not _close(
                    entity.dxf.get("line_spacing_factor", 1.0),
                    record["line_spacing_factor"],
                )
                or int(entity.dxf.get("line_spacing_style", 1))
                != record["line_spacing_style"]
            ):
                raise ReadbackError(f"MTEXT layout drift for {identity}")
            expected_format = _mtext_format_signature(expected_content)
            actual_format = _mtext_format_signature(entity.text)
            if actual_format != expected_format:
                raise ReadbackError(f"MTEXT effective format drift for {identity}")
            box = _mtext_glyph_box(
                entity, doc, font_path, font_profile, factor, offset_x,
                native_technical=record["kind"] == "technical",
            )
        else:
            expected_hv = (record["halign"], record["valign"])
            if (
                int(entity.dxf.get("halign", 0)),
                int(entity.dxf.get("valign", 0)),
            ) != expected_hv:
                raise ReadbackError(f"text alignment drift for {identity}")
            actual_point = entity.dxf.align_point if any(expected_hv) else entity.dxf.insert
            height = entity.dxf.height
            if not _close(entity.dxf.get("width", 1.0), record["width_factor"]):
                raise ReadbackError(f"text width-factor drift for {identity}")
            box = aligned_box_mm(
                actual,
                tuple(record["point_mm"]),
                record["height_mm"],
                font_profile,
                _text_alignment(entity),
                record["width_factor"],
                record.get("rotation", 0.0),
            )
        _require_point(actual_point, (offset_x + point[0] * factor, point[1] * factor), "text insertion")
        if not _close(height, record["height_mm"] * factor):
            raise ReadbackError(f"text height drift for {identity}")
        rotation = entity.get_rotation() if entity.dxftype() == "MTEXT" else entity.dxf.get("rotation", 0.0)
        if entity.dxf.style != record["style"] or not _close(rotation, record.get("rotation", 0.0)):
            raise ReadbackError(f"text style/rotation drift for {identity}")
        extrusion = entity.dxf.get("extrusion", Vec3(0.0, 0.0, 1.0))
        text_display_drift = entity.dxftype() == "TEXT" and (
            not _close(entity.dxf.get("oblique", 0.0), 0.0)
            or int(entity.dxf.get("text_generation_flag", 0)) != 0
            or not _close(entity.dxf.get("thickness", 0.0), 0.0)
        )
        if text_display_drift or not (
            _close(extrusion.x, 0.0)
            and _close(extrusion.y, 0.0)
            and _close(extrusion.z, 1.0)
        ):
            raise ReadbackError(f"text effective display properties drift for {identity}")
        bounds = record.get("bounds_mm")
        bounds_tolerance = float(record.get("bounds_tolerance_mm", 0.1))
        if bounds is not None and not box_inside(
            box, bounds, tolerance=bounds_tolerance
        ):
            raise ReadbackError(f"text glyph bounds leave controlled cell for {identity}: {box}")
        if not box_inside(box, [0.0, 0.0, 210.0, 297.0], tolerance=0.0):
            raise ReadbackError(f"text glyph bounds leave paper for {identity}: {box}")
        frame_crossings = _frame_crossing_indexes(box, layout)
        allowed_crossings = record.get("allowed_frame_crossings", [])
        if frame_crossings != allowed_crossings:
            raise ReadbackError(
                f"text glyph/frame crossing drift for {identity}: "
                f"actual={frame_crossings}, allowed={allowed_crossings}, box={box}"
            )
        measurements.append({
            "identity": "/".join(identity),
            "text": actual,
            "entity_type": entity.dxftype(),
            **({"measurement_backend": "opencadstudio_hz_vector_glyphs"}
               if record["kind"] == "technical" and font_profile.get("native_hz_technical_metrics") else {}),
            "raw_text": entity.text if entity.dxftype() == "MTEXT" else entity.dxf.text,
            "point_paper_mm": [point[0], point[1]],
            "box_paper_mm": box,
            "cell_mm": bounds,
            "cap_height_mm": record["height_mm"],
            "style": record["style"],
            "flow_direction": (
                int(entity.dxf.get("flow_direction", 1))
                if entity.dxftype() == "MTEXT"
                else None
            ),
            "effective_format": (
                actual_format if entity.dxftype() == "MTEXT" else None
            ),
            "frame_crossings": frame_crossings,
        })
        handles[f"{record['kind']}:{record['id']}"] = entity.dxf.handle
    clearance = 0.01
    for index, first in enumerate(measurements):
        a = first["box_paper_mm"]
        for second in measurements[index + 1:]:
            b = second["box_paper_mm"]
            if (
                min(a[2], b[2]) - max(a[0], b[0]) > clearance
                and min(a[3], b[3]) - max(a[1], b[1]) > clearance
            ):
                raise ReadbackError(
                    "editable text glyph bounds overlap: "
                    f"{first['identity']} / {second['identity']}"
                )
    return handles, measurements


def _validate_frame(msp, layout: dict, expected_pages: list[DrawingPage]) -> None:
    lines = [entity for entity in msp.query("LINE") if len(_xdata(entity)) >= 2 and _xdata(entity)[:2] == ("template", "frame-line")]
    if len(lines) != len(layout["frame_lines_mm"]) * len(expected_pages):
        raise ReadbackError("controlled native frame entity count mismatch")
    for page in expected_pages:
        offset = float(page.placement.model_origin_mm.x)
        factor = float(page.scale.denominator)
        for index, expected in enumerate(layout["frame_lines_mm"]):
            identity = ("template", "frame-line", str(index))
            matches = [entity for entity in lines if _xdata(entity) == identity
                       and _close(entity.dxf.start.x, offset + expected[0] * factor)
                       and _close(entity.dxf.start.y, expected[1] * factor)
                       and _close(entity.dxf.end.x, offset + expected[2] * factor)
                       and _close(entity.dxf.end.y, expected[3] * factor)
                       and entity.dxf.layer == expected[4]
                       and int(entity.dxf.get("color", 256)) == expected[5]
                       and entity.dxf.get("true_color", None) == expected[6]
                       and str(entity.dxf.get("linetype", "BYLAYER")).upper() == str(expected[7]).upper()]
            if len(matches) != 1:
                raise ReadbackError(f"controlled frame line missing/drifted: {page.row_id}/{index}")


def _validate_geometry_bounds(entities, page: DrawingPage, factor: float, offset_x: float, layout: dict) -> tuple[float, float, float, float]:
    cache = bbox.Cache()
    extent = bbox.extents(entities, cache=cache)
    if not extent.has_data:
        raise ReadbackError(f"geometry bounds unavailable for {page.row_id}")
    paper = (extent.extmin.x - offset_x, extent.extmin.y, extent.extmax.x - offset_x, extent.extmax.y)
    paper = tuple(value / factor for value in paper)
    area = layout["drawing_area_mm"]
    if paper[0] < area["left"] - 0.1 or paper[1] < area["bottom"] - 0.1 or paper[2] > area["right"] + 0.1 or paper[3] > area["top"] + 0.1:
        raise ReadbackError(f"heater/lead/dimension bounds leave drawing area for {page.row_id}: {paper}")
    for zone in layout["forbidden_zones_mm"]:
        overlap = paper[0] < zone["right"] and paper[2] > zone["left"] and paper[1] < zone["top"] and paper[3] > zone["bottom"]
        if overlap:
            raise ReadbackError(f"heater/lead/dimension collision with {zone['name']} for {page.row_id}")
    return paper


def _validate_lead_dimension_clearance(leads, dimensions, text_measurements, factor, offset_x):
    """Check actual rendered dimension lines, arrows and glyphs against leads."""
    obstacles = []
    for dimension in dimensions:
        for entity in dimension.virtual_entities():
            if entity.dxftype() in {"TEXT", "MTEXT", "POINT"}:
                continue
            extent = bbox.extents([entity])
            if extent.has_data:
                obstacles.append(((extent.extmin.x-offset_x)/factor, extent.extmin.y/factor,
                                  (extent.extmax.x-offset_x)/factor, extent.extmax.y/factor))
    obstacles.extend(item["box_paper_mm"] for item in text_measurements.values())
    minimum = float("inf")
    for lead in leads:
        # Leads and native linear dimension strokes are axis aligned. INSERT
        # bounds include filled arrows, and text uses the locked font glyphs.
        a = (min(lead.dxf.start.x, lead.dxf.end.x)-offset_x)/factor
        b = min(lead.dxf.start.y, lead.dxf.end.y)/factor
        c = (max(lead.dxf.start.x, lead.dxf.end.x)-offset_x)/factor
        d = max(lead.dxf.start.y, lead.dxf.end.y)/factor
        for x1,y1,x2,y2 in obstacles:
            dx = max(x1-c, a-x2, 0.0)
            dy = max(y1-d, b-y2, 0.0)
            distance = (dx*dx+dy*dy)**0.5
            minimum = min(minimum, distance)
    if minimum < 0.25:
        raise ReadbackError(f"lead/dimension clearance below 0.25 paper mm: {minimum:g}")
    return minimum


def inspect_dxf(path: Path, expected_pages: list[DrawingPage], layout: dict | None = None, font_profile: dict | None = None) -> dict[str, Any]:
    try:
        doc = ezdxf.readfile(path)
    except (OSError, ezdxf.DXFError) as exc:
        raise ReadbackError(f"cannot read DXF: {exc}") from exc
    if layout is None:
        root = Path(__file__).resolve().parents[4]
        import json
        layout = json.loads((root / "templates/heater-a4-v1/layout.json").read_text(encoding="utf-8"))
    if font_profile is None:
        import json
        root = Path(__file__).resolve().parents[4]
        font_profile = json.loads((root / "templates/heater-a4-v1/fonts.json").read_text(encoding="utf-8"))
    if doc.dxfversion != DXF_PDF_PROFILE.dxf_acad_version:
        raise ReadbackError(f"unexpected DXF version: {doc.dxfversion}")
    if int(doc.header.get("$INSUNITS", 0)) != DXF_PDF_PROFILE.insunits:
        raise ReadbackError("DXF unit drift: INSUNITS is not millimetres")
    try:
        style = doc.styles.get(font_profile["cad_style_name"])
        dimstyle = doc.dimstyles.get(font_profile["dimension_style_name"])
        font_path, font_index = locked_font_path(font_profile)
        font = locked_font(font_profile)
    except (KeyError, ValueError) as exc:
        raise ReadbackError(f"locked font/style profile is unavailable: {exc}") from exc
    dimension_text_style = doc.styles.get(font_profile["dimension_text_style"])
    if (
        style.dxf.font != font_profile["cad_style_font_file"]
        or str(style.dxf.get("bigfont", "")).lower()
        != font_profile["cad_style_bigfont_file"].lower()
    ):
        raise ReadbackError("original HZ SHX style dependency drift")
    if (
        not _close(style.dxf.get("height", 0.0), 0.0)
        or not _close(
            style.dxf.get("width", 1.0), font_profile["cad_style_width_factor"]
        )
        or not _close(style.dxf.get("oblique", 0.0), 0.0)
        or int(style.dxf.get("generation_flags", 0)) != 0
    ):
        raise ReadbackError("original HZ effective display properties drift")
    if dimension_text_style.dxf.font != font_profile.get("dimension_cad_font_file", font_profile["render_cad_style_font_file"]):
        raise ReadbackError("HEATER_CJK font filename drift")
    if (
        not _close(dimension_text_style.dxf.get("height", 0.0), 0.0)
        or not _close(dimension_text_style.dxf.get("width", 1.0), font_profile.get("dimension_style_width_factor", 1.0))
        or not _close(dimension_text_style.dxf.get("oblique", 0.0), 0.0)
        or int(dimension_text_style.dxf.get("generation_flags", 0)) != 0
        or str(dimension_text_style.dxf.get("bigfont", "")) != ""
    ):
        raise ReadbackError("HEATER_CJK effective display properties drift")
    if dimstyle.dxf.dimtxsty != font_profile["dimension_text_style"]:
        raise ReadbackError("HEATER_DIM text-style association drift")
    linetype_error = controlled_dimension_linetype_error(
        doc, dimstyle_name=font_profile["dimension_style_name"]
    )
    if linetype_error:
        raise ReadbackError(linetype_error)
    for name, expected in dimension_style_values(font_profile).items():
        actual = dimstyle.dxf.get(name)
        if isinstance(expected, float):
            matches = _close(actual, expected)
        else:
            matches = int(actual) == expected
        if not matches:
            raise ReadbackError(f"HEATER_DIM controlled setting drift: {name}")
    if font["name"].getDebugName(1) != font_profile["face_family"] or font["name"].getDebugName(6) != font_profile["face_postscript_name"]:
        raise ReadbackError("locked font face identity drift")
    dependencies = font_profile.get("cad_dependencies")
    if not isinstance(dependencies, list) or len(dependencies) != 2:
        raise ReadbackError("CAD font dependency profile is incomplete")
    expected_dependency = dependencies[0]
    if (
        expected_dependency.get("style") != font_profile["cad_style_name"]
        or expected_dependency.get("font_file") != style.dxf.font
        or expected_dependency.get("bigfont_file").lower()
        != str(style.dxf.get("bigfont", "")).lower()
        or expected_dependency.get("source_sha256")
        != font_profile["original_hzdx_shx"]["sha256"]
        or expected_dependency.get("license") != "unknown"
    ):
        raise ReadbackError("original SHX dependency identity/hash/policy drift")
    render_dependency = dependencies[1]
    if (
        render_dependency.get("style") != font_profile["dimension_text_style"]
        or render_dependency.get("font_file") != font_profile["render_cad_style_font_file"]
        or render_dependency.get("postscript") != font_profile["face_postscript_name"]
        or render_dependency.get("sha256") != font_profile["extracted_face_sha256"]
        or render_dependency.get("license") != "SIL Open Font License 1.1"
    ):
        raise ReadbackError("render font dependency identity/hash/license drift")
    if "Layout1" in doc.layout_names():
        raise ReadbackError("uncontrolled default Layout1 is forbidden")
    layer_error = controlled_layer_error(doc)
    if layer_error:
        raise ReadbackError(layer_error)
    msp = doc.modelspace()
    unknown = sorted({entity.dxftype() for entity in msp if entity.dxftype() not in ALLOWED_MODELSPACE_TYPES})
    if unknown:
        raise ReadbackError(f"unsupported modelspace entities: {', '.join(unknown)}")
    for entity in msp:
        if entity.dxftype() == "DIMENSION":
            continue
        display_error = controlled_entity_display_error(entity, top_level=True)
        if display_error:
            raise ReadbackError(f"{entity.dxftype()} {display_error}")
    heaters = list(msp.query("LWPOLYLINE[layer=='HEATER']"))
    leads = list(msp.query("LINE[layer=='HEATER_LEAD']"))
    dimensions = list(msp.query("DIMENSION[layer=='DIMENSION']"))
    texts = list(msp.query("TEXT MTEXT"))
    _validate_frame(msp, layout, expected_pages)
    if len(heaters) != len(expected_pages) or len(leads) != 2 * len(expected_pages) or len(dimensions) != 2 * len(expected_pages):
        raise ReadbackError("heater/lead/native DIMENSION entity count mismatch")
    page_checks = []
    for page in expected_pages:
        rectangle = _one(heaters, (page.row_id, "heater", page.code), "heater")
        expected_left = float(page.geometry_mm.rectangle.origin.x)
        actual_left = float(list(rectangle.get_points("xy"))[0][0])
        offset_x = actual_left - expected_left
        width, length = _validate_rectangle(rectangle, page, offset_x)
        page_leads = []
        handles = {"heater": rectangle.dxf.handle}
        for index, expected in enumerate(page.geometry_mm.lead_segments):
            entity = _one(leads, (page.row_id, "lead", str(index)), "lead")
            start, end = _point(expected.start), _point(expected.end)
            _require_point(entity.dxf.start, (start[0] + offset_x, start[1]), "lead start")
            _require_point(entity.dxf.end, (end[0] + offset_x, end[1]), "lead end")
            page_leads.append(entity)
            handles[f"lead:{index}"] = entity.dxf.handle
        measured = {}
        dimension_cache_semantics: dict[str, list[dict[str, Any]]] = {}
        dimension_text_measurements: dict[str, dict[str, Any]] = {}
        dimension_parent_display: dict[str, dict[str, Any]] = {}
        dimension_linetype_sources: dict[str, dict[str, Any]] = {}
        page_dimensions = []
        origin = page.geometry_mm.rectangle.origin
        left, bottom = float(origin.x) + offset_x, float(origin.y)
        right, top = left + width, bottom + length
        factor = float(page.scale.denominator)
        placement_profile = layout["dimension_placement_paper_mm"]
        placement = placement_profile.get("sample_overrides", {}).get(
            page.code, placement_profile["fallback"]
        )
        width_dim_offset = float(placement["width_offset"]) * factor
        length_dim_offset = float(placement["length_offset"]) * factor
        requested_side = placement["length_side"]
        right_side = (
            page.fields.lead_side.value == "long" and width != length
            if requested_side == "auto"
            else requested_side == "right"
        )
        for kind, value in (("width", width), ("length", length)):
            entity = _one(dimensions, (page.row_id, "dimension", kind), "dimension")
            display_error = controlled_entity_display_error(entity, top_level=True)
            if display_error:
                raise ReadbackError(
                    f"dimension effective display properties drift for {page.row_id}/{kind}: "
                    f"{display_error}"
                )
            if _cache_display_signature(entity, factor) != {
                "true_color": None,
                "transparency": None,
                "ltscale": 1.0,
                "invisible": 0,
                "material_handle": "0",
                "plotstyle_handle": "0",
                "shadow_mode": 0,
                "visualstyle_handle": "0",
                "extrusion": [0.0, 0.0, 1.0],
                "thickness": 0.0,
            }:
                raise ReadbackError(f"dimension effective display properties drift for {page.row_id}/{kind}")
            if entity.dxf.text not in {"", "<>"}:
                raise ReadbackError(f"dimension display override is forbidden for {page.row_id}/{kind}")
            if not _close(entity.get_measurement(), value, DXF_PDF_PROFILE.dimension_tolerance_mm):
                raise ReadbackError(f"native {kind} dimension drift for {page.row_id}")
            virtual = list(entity.virtual_entities())
            overrides = entity.get_acad_dstyle(doc.dimstyles.get(entity.dxf.dimstyle))
            expected_overrides = {"dimscale": factor, **profile_dimension_overrides(font_profile, page.code)}
            if entity.dxf.dimstyle != font_profile["dimension_style_name"] or any(not _close(overrides.get(name, float("nan")), value) for name, value in expected_overrides.items()):
                raise ReadbackError(f"dimension style/display multiplier drift for {page.row_id}/{kind}")
            linetype_error = controlled_dimension_linetype_error(doc, entity)
            if linetype_error:
                raise ReadbackError(
                    f"dimension regeneration source drift for {page.row_id}/{kind}: "
                    f"{linetype_error}"
                )
            if kind == "width":
                dim_offset = width_dim_offset
                expected_defpoint = (left, bottom - dim_offset)
                expected_midpoint = ((left + right) / 2.0, bottom - dim_offset)
                expected_angle = 0.0
                expected_arrows = [
                    (expected_defpoint, 180.0),
                    ((right, bottom - dim_offset), 0.0),
                ]
                _require_point(entity.dxf.defpoint2, (left, bottom), "width dimension p1")
                _require_point(entity.dxf.defpoint3, (right, bottom), "width dimension p2")
            else:
                dim_offset = length_dim_offset
                x = right if right_side else left
                _require_point(entity.dxf.defpoint2, (x, bottom), "length dimension p1")
                _require_point(entity.dxf.defpoint3, (x, top), "length dimension p2")
                expected_base = right + dim_offset if right_side else left - dim_offset
                if not _close(entity.dxf.defpoint.x, expected_base):
                    raise ReadbackError(f"length dimension side drift for {page.row_id}")
                expected_defpoint = (expected_base, bottom)
                expected_midpoint = (expected_base, (bottom + top) / 2.0)
                expected_angle = 90.0
                expected_arrows = [
                    (expected_defpoint, 270.0),
                    ((expected_base, top), 90.0),
                ]
            expected_cache_signature = _expected_dimension_cache_signature(
                kind=kind,
                left=left,
                bottom=bottom,
                right=right,
                top=top,
                dim_offset=dim_offset,
                factor=factor,
                offset_x=offset_x,
                long_lead=right_side,
                font_profile=font_profile,
                dimstyle_linetypes={
                    name: dimstyle.dxf.get(name, None)
                    for name in CONTROLLED_DIMENSION_LINETYPE_FIELDS
                },
                dimension_overrides={**overrides, **expected_overrides},
            )
            # Narrow paper dimensions legitimately move text and reverse arrows.
            # Reconstruct with the controlled style, never infer from the candidate cache.
            expected_text = next(item for item in expected_cache_signature if item["type"] == "MTEXT")
            expected_midpoint = (
                expected_text["insert"][0] * factor + offset_x,
                expected_text["insert"][1] * factor,
            )
            if value < (2 * expected_overrides["dimasz"] + CONTROLLED_DIMSTYLE_VALUES["dimgap"]) * factor:
                expected_arrows = [(point, (angle + 180) % 360) for point, angle in expected_arrows]
            _require_point(entity.dxf.defpoint, expected_defpoint, f"{kind} dimension line origin")
            _require_point(entity.dxf.text_midpoint, expected_midpoint, f"{kind} dimension text midpoint")
            if not _angle_close(entity.dxf.get("angle", 0.0), expected_angle):
                raise ReadbackError(f"dimension angle drift for {page.row_id}/{kind}")
            dimension_text = [item for item in virtual if item.dxftype() in {"TEXT", "MTEXT"}]
            if (
                len(dimension_text) != 1
                or dimension_text[0].dxftype() != "MTEXT"
                or dimension_text[0].dxf.style != font_profile["dimension_text_style"]
            ):
                raise ReadbackError(f"dimension font style drift for {page.row_id}/{kind}")
            cached = dimension_text[0]
            cached_text = cached.dxf.text if cached.dxftype() == "TEXT" else cached.plain_text()
            expected_cached = _controlled_dimension_text(value)
            if cached_text != expected_cached:
                raise ReadbackError(f"dimension cached display text drift for {page.row_id}/{kind}")
            cached_insert = cached.dxf.insert
            if not (_close(cached_insert.x, expected_midpoint[0]) and _close(cached_insert.y, expected_midpoint[1])):
                raise ReadbackError(f"dimension cached display position drift for {page.row_id}/{kind}")
            if int(cached.dxf.get("attachment_point", 0)) != 5 or not _angle_close(cached.get_rotation(), expected_angle):
                raise ReadbackError(f"dimension cached display orientation drift for {page.row_id}/{kind}")
            cached_height = float(cached.dxf.height if cached.dxftype() == "TEXT" else cached.dxf.char_height)
            if not _close(cached_height, expected_overrides["dimtxt"] * factor):
                raise ReadbackError(f"dimension cached display height drift for {page.row_id}/{kind}")
            dimension_text_measurements[kind] = {
                "text": cached_text,
                "style": cached.dxf.style,
                "cap_height_paper_mm": cached_height / factor,
                "box_paper_mm": _single_line_mtext_glyph_box(
                    cached, cached_text, font_profile, factor, offset_x
                ),
            }
            arrows = [item for item in virtual if item.dxftype() == "INSERT"]
            if len(arrows) != 2:
                raise ReadbackError(f"dimension arrow INSERT count drift for {page.row_id}/{kind}")
            remaining = list(expected_arrows)
            for arrow in arrows:
                matches = [
                    expected for expected in remaining
                    if _close(arrow.dxf.insert.x, expected[0][0])
                    and _close(arrow.dxf.insert.y, expected[0][1])
                    and _angle_close(arrow.dxf.get("rotation", 0.0), expected[1])
                ]
                if (
                    arrow.dxf.name != "_CLOSEDFILLED"
                    or len(matches) != 1
                    or not _close(arrow.dxf.get("xscale", 1.0), expected_overrides["dimasz"] * factor)
                    or not _close(arrow.dxf.get("yscale", 1.0), expected_overrides["dimasz"] * factor)
                    or not _close(arrow.dxf.get("zscale", 1.0), 1.0)
                ):
                    raise ReadbackError(f"dimension arrow geometry drift for {page.row_id}/{kind}")
                remaining.remove(matches[0])
            solid_count = _solid_count(virtual)
            if solid_count != 2:
                raise ReadbackError(f"dimension arrow SOLID loss for {page.row_id}/{kind}")
            cache_signature = _dimension_cache_signature(virtual, offset_x, factor)
            if cache_signature != expected_cache_signature:
                raise ReadbackError(
                    f"dimension complete visible cache semantics drift for {page.row_id}/{kind}"
                )
            dimension_cache_semantics[kind] = cache_signature
            dimension_parent_display[kind] = controlled_entity_display_signature(entity)
            dimension_linetype_sources[kind] = controlled_dimension_linetype_signature(
                doc, entity
            )
            measured[kind] = entity.get_measurement()
            page_dimensions.append(entity)
            handles[f"dimension:{kind}"] = entity.dxf.handle
        text_handles, text_measurements = _validate_texts(
            texts,
            doc,
            layout,
            page,
            factor,
            offset_x,
            font_profile,
            font_path,
        )
        handles.update(text_handles)
        handles["viewport"] = _validate_viewport(doc, page, offset_x)
        geometry_box = _validate_geometry_bounds([rectangle, *page_leads, *page_dimensions], page, factor, offset_x, layout)
        lead_clearance = _validate_lead_dimension_clearance(page_leads, page_dimensions, dimension_text_measurements, factor, offset_x)
        all_boxes = [
            geometry_box,
            *(item["box_paper_mm"] for item in text_measurements),
            *(item["box_paper_mm"] for item in dimension_text_measurements.values()),
        ]
        page_box = [min(box[0] for box in all_boxes), min(box[1] for box in all_boxes),
                    max(box[2] for box in all_boxes), max(box[3] for box in all_boxes)]
        if not box_inside(tuple(page_box), [0.0, 0.0, 210.0, 297.0], tolerance=0.0):
            raise ReadbackError(f"complete content bounds leave paper for {page.row_id}: {page_box}")
        page_checks.append({"row_id": page.row_id, "code": page.code,
                            "geometry_mm": {"width": width, "length": length},
                            "native_dimensions_mm": measured, "scale": page.scale.label,
                            "entity_handles": handles, "paper_position_tolerance_mm": 0.1,
                            "geometry_lead_dimension_box_paper_mm": geometry_box,
                            "lead_dimension_min_clearance_paper_mm": lead_clearance,
                            "complete_content_box_paper_mm": page_box,
                            "controlled_layer_display": controlled_layer_signature(doc),
                            "dimension_parent_display": dimension_parent_display,
                            "dimension_linetype_sources": dimension_linetype_sources,
                            "dimension_cache_semantics": dimension_cache_semantics,
                            "dimension_text_measurements": dimension_text_measurements,
                            "dimension_regeneration_semantics": "matches independently reconstructed controlled DIMSTYLE cache"})
        page_checks[-1]["text_measurements"] = text_measurements
    expected_text_count = len(expected_text_records(layout, expected_pages[0])) * len(expected_pages)
    if len(texts) != expected_text_count:
        raise ReadbackError(f"unexpected editable text entity count: {len(texts)}")
    coverage_texts = [
        entity.dxf.text if entity.dxftype() == "TEXT" else entity.plain_text()
        for entity in texts
    ]
    coverage_texts.extend(
        f"{value:g}"
        for page in expected_pages
        for value in (
            float(page.geometry_mm.rectangle.width_mm),
            float(page.geometry_mm.rectangle.length_mm),
        )
    )
    try:
        check_glyph_coverage(font_path, coverage_texts, face_index=font_index if font_path.suffix.lower() in {".ttc", ".otc"} else None)
    except ValueError as exc:
        raise ReadbackError(f"locked font coverage failed: {exc}") from exc
    return {
        "status": "passed", "path": str(path), "dxf_version": doc.dxfversion,
        "insunits": int(doc.header["$INSUNITS"]), "unit": "mm",
        "entity_types": dict(sorted((kind, len(list(msp.query(kind)))) for kind in {e.dxftype() for e in msp})),
        "editable_text_entities": len(texts), "native_dimension_entities": len(dimensions),
        "dimension_arrow_solids": 2 * len(dimensions),
        "controlled_layer_display": controlled_layer_signature(doc), "pages": page_checks,
    }
