"""Shared effective-display policy for the controlled B02 DXF/PDF profile."""

from __future__ import annotations

from typing import Any

import ezdxf

from .profile import CONTROLLED_DIMENSION_LINETYPE_FIELDS


CONTROLLED_LAYER_DISPLAY: dict[str, dict[str, Any]] = {
    "0": {"color": 7, "linetype": "Continuous", "lineweight": -3, "plot": 1},
    "___SHELL": {"color": 7, "linetype": "Continuous", "lineweight": -3, "plot": 1},
    "加热器": {"color": 5, "linetype": "Continuous", "lineweight": 50, "plot": 1},
    "Defpoints": {"color": 7, "linetype": "Continuous", "lineweight": -3, "plot": 0},
    "标注": {"color": 201, "linetype": "Continuous", "lineweight": -3, "plot": 1},
    "text": {"color": 7, "linetype": "Continuous", "lineweight": -3, "plot": 1},
    "图纸底框": {"color": 1, "linetype": "Continuous", "lineweight": 50, "plot": 1},
    "TU": {"color": 250, "linetype": "Continuous", "lineweight": 30, "plot": 1},
    "加热片": {"color": 1, "linetype": "Continuous", "lineweight": 50, "plot": 1},
    "1": {"color": 1, "linetype": "Continuous", "lineweight": 50, "plot": 1},
    "主动加热器": {"color": 1, "linetype": "Continuous", "lineweight": -3, "plot": 1},
    "热电偶": {"color": 30, "linetype": "Continuous", "lineweight": 50, "plot": 1},
    "喷漆保护": {"color": 9, "linetype": "Continuous", "lineweight": -3, "plot": 1},
    "尺寸": {"color": 223, "true_color": 15293355, "linetype": "Continuous", "lineweight": -3, "plot": 1},
    "HEATER": {"color": 7, "linetype": "Continuous", "lineweight": 25, "plot": 1},
    "HEATER_LEAD": {"color": 7, "linetype": "Continuous", "lineweight": 18, "plot": 1},
    "DIMENSION": {"color": 7, "linetype": "Continuous", "lineweight": 18, "plot": 1},
}

_CONTINUOUS_PATTERN_TAGS = [[72, 65], [73, 0], [40, 0.0]]


def _value(entity, name: str, default):
    return entity.dxf.get(name, default) if entity.dxf.is_supported(name) else default


def _xdata(entity) -> tuple[str, ...]:
    try:
        return tuple(
            str(value)
            for code, value in entity.get_xdata("HEATER_DRAWING")
            if code == 1000
        )
    except ezdxf.DXFValueError:
        return ()


def _normalized_linetype_tag_value(value):
    if isinstance(value, float):
        normalized = round(value, 12)
        return 0.0 if normalized == 0.0 else normalized
    return value


def controlled_linetype_signature(doc, name: str) -> dict[str, Any]:
    """Return the display-relevant definition of one referenced LTYPE entry."""
    linetype = doc.linetypes.get(name)
    pattern = linetype.pattern_tags
    return {
        "name": str(linetype.dxf.name),
        "is_complex": bool(pattern.is_complex_type()),
        "compiled_pattern": [
            _normalized_linetype_tag_value(float(value))
            for value in pattern.compile()
        ],
        "pattern_tags": [
            [int(tag.code), _normalized_linetype_tag_value(tag.value)]
            for tag in pattern.tags
        ],
    }


def _controlled_linetype_error(doc, name: str) -> str | None:
    try:
        signature = controlled_linetype_signature(doc, name)
    except ezdxf.DXFTableEntryError:
        return f"controlled linetype is missing: {name}"
    if name.upper() == "CONTINUOUS" and signature != {
        "name": signature["name"],
        "is_complex": False,
        "compiled_pattern": [],
        "pattern_tags": _CONTINUOUS_PATTERN_TAGS,
    }:
        return "controlled linetype definition drift: Continuous"
    if name.upper() != "CONTINUOUS":
        return f"controlled linetype is outside the display profile: {name}"
    return None


def _dimension_linetype_sources(doc, dimension=None, dimstyle_name: str | None = None):
    if dimension is not None:
        dimstyle_name = str(dimension.dxf.get("dimstyle", "Standard"))
    if not dimstyle_name:
        raise ezdxf.DXFTableEntryError("dimension style name is missing")
    dimstyle = doc.dimstyles.get(dimstyle_name)
    overrides = (
        dimension.get_acad_dstyle(dimstyle) if dimension is not None else {}
    )
    result = {}
    for field in CONTROLLED_DIMENSION_LINETYPE_FIELDS:
        if field in overrides:
            origin = "dimension_override"
            value = overrides[field]
        else:
            origin = "dimstyle"
            value = dimstyle.dxf.get(field, None)
        result[field] = (origin, value)
    return dimstyle, result


def controlled_dimension_linetype_error(
    doc, dimension=None, *, dimstyle_name: str | None = None
) -> str | None:
    """Reject a DIMSTYLE/override source that can regenerate non-profile lines."""
    try:
        _dimstyle, sources = _dimension_linetype_sources(
            doc, dimension, dimstyle_name
        )
    except (ezdxf.DXFTableEntryError, ezdxf.DXFValueError) as exc:
        return f"controlled dimension linetype source is unavailable: {exc}"
    for field, (origin, value) in sources.items():
        # None is the omitted ezdxf default; explicit Continuous is the only
        # equivalent named source in this profile.
        if value is not None and str(value).upper() != "CONTINUOUS":
            return (
                "controlled dimension linetype source is outside the display "
                f"profile: {origin}.{field}={value}"
            )
        error = _controlled_linetype_error(doc, "Continuous")
        if error:
            return error
    return None


def controlled_dimension_linetype_signature(
    doc, dimension=None, *, dimstyle_name: str | None = None
) -> dict[str, Any]:
    """Bind all actual native-dimension regeneration line-type sources."""
    error = controlled_dimension_linetype_error(
        doc, dimension, dimstyle_name=dimstyle_name
    )
    if error:
        raise ValueError(error)
    dimstyle, sources = _dimension_linetype_sources(
        doc, dimension, dimstyle_name
    )
    definition = controlled_linetype_signature(doc, "Continuous")
    return {
        "dimstyle": str(dimstyle.dxf.name),
        "fields": {
            field: {
                "origin": origin,
                "source": (
                    "omitted_default"
                    if value is None
                    else "Continuous"
                ),
                "effective_linetype": "Continuous",
                "linetype_definition": definition,
            }
            for field, (origin, value) in sources.items()
        },
    }


def controlled_layer_signature(doc) -> dict[str, dict[str, Any]]:
    signature: dict[str, dict[str, Any]] = {}
    linetype_signatures: dict[str, dict[str, Any]] = {}
    for layer in doc.layers:
        linetype_name = str(layer.dxf.get("linetype", "Continuous"))
        if linetype_name not in linetype_signatures:
            linetype_signatures[linetype_name] = controlled_linetype_signature(
                doc, linetype_name
            )
        signature[str(layer.dxf.name)] = {
            "color": int(layer.dxf.color),
            "true_color": layer.dxf.get("true_color", None),
            "transparency": round(float(layer.transparency), 12),
            "linetype": linetype_name,
            "linetype_definition": linetype_signatures[linetype_name],
            "lineweight": int(layer.dxf.get("lineweight", -3)),
            "plot": int(layer.dxf.get("plot", 1)),
            "off": bool(layer.is_off()),
            "frozen": bool(layer.is_frozen()),
            "locked": bool(layer.is_locked()),
        }
    return dict(sorted(signature.items()))


def controlled_entity_display_signature(entity) -> dict[str, Any]:
    extrusion = _value(entity, "extrusion", ezdxf.math.Vec3(0.0, 0.0, 1.0))
    return {
        "layer": str(entity.dxf.get("layer", "0")),
        "color": int(entity.dxf.get("color", 256)),
        "true_color": _value(entity, "true_color", None),
        "transparency": _value(entity, "transparency", None),
        "linetype": str(entity.dxf.get("linetype", "BYLAYER")),
        "ltscale": round(float(_value(entity, "ltscale", 1.0)), 12),
        "lineweight": int(entity.dxf.get("lineweight", -1)),
        "invisible": int(_value(entity, "invisible", 0)),
        "material_handle": str(_value(entity, "material_handle", "0")),
        "plotstyle_handle": str(_value(entity, "plotstyle_handle", "0")),
        "shadow_mode": int(_value(entity, "shadow_mode", 0)),
        "visualstyle_handle": str(_value(entity, "visualstyle_handle", "0")),
        "extrusion": [round(float(component), 12) for component in extrusion],
        "thickness": round(float(_value(entity, "thickness", 0.0)), 12),
    }


def controlled_layer_error(doc) -> str | None:
    """Reject any layer state that can change the controlled effective display."""
    actual_names = {layer.dxf.name for layer in doc.layers}
    expected_names = set(CONTROLLED_LAYER_DISPLAY)
    if actual_names != expected_names:
        return "controlled layer table membership drift"
    for name, expected in CONTROLLED_LAYER_DISPLAY.items():
        try:
            layer = doc.layers.get(name)
        except ezdxf.DXFTableEntryError:
            return f"controlled layer is missing: {name}"
        if (
            layer.is_off()
            or layer.is_frozen()
            or layer.is_locked()
            or int(layer.dxf.color) != expected["color"]
            or str(layer.dxf.get("linetype", "Continuous")).upper() != expected["linetype"].upper()
            or int(layer.dxf.get("lineweight", -3)) != expected["lineweight"]
            or int(layer.dxf.get("plot", 1)) != expected["plot"]
            or layer.dxf.get("true_color", None) != expected.get("true_color")
            or abs(float(layer.transparency)) > 1e-12
        ):
            return f"controlled layer effective display drift: {name}"
    for linetype_name in sorted(
        {str(item["linetype"]) for item in CONTROLLED_LAYER_DISPLAY.values()}
    ):
        error = _controlled_linetype_error(doc, linetype_name)
        if error:
            return error
    return None


def controlled_entity_display_error(
    entity,
    *,
    top_level: bool = False,
    dimension_cache: bool = False,
    block_child: bool = False,
) -> str | None:
    """Validate display attributes and BYLAYER/BYBLOCK roles for one entity."""
    extrusion = _value(entity, "extrusion", ezdxf.math.Vec3(0.0, 0.0, 1.0))
    if int(_value(entity, "invisible", 0)) != 0:
        return "invisible entities are outside the controlled display profile"
    identity = _xdata(entity)
    native_frame = len(identity) == 3 and identity[:2] == ("template", "frame-line")
    native_text = (
        len(identity) == 3
        and identity[1] in {"fixed", "field", "technical"}
        and entity.dxftype() in {"TEXT", "MTEXT"}
    )
    if native_frame:
        if str(entity.dxf.get("layer", "0")) == "图纸底框":
            if (
                int(entity.dxf.get("color", 256)) != 40
                or _value(entity, "true_color", None) != 16308017
                or str(entity.dxf.get("linetype", "BYLAYER")).upper() != "BYLAYER"
                or int(entity.dxf.get("lineweight", -1)) != -3
            ):
                return "native yellow frame display binding drift"
        elif str(entity.dxf.get("layer", "0")) == "0":
            if (
                int(entity.dxf.get("color", 256)) not in {7, 256}
                or _value(entity, "true_color", None) is not None
                or str(entity.dxf.get("linetype", "BYLAYER")).upper() not in {"BYLAYER", "CONTINUOUS"}
                or int(entity.dxf.get("lineweight", -1)) != -3
            ):
                return "native black frame display binding drift"
        else:
            return "native frame layer binding drift"
    elif native_text:
        if (
            str(entity.dxf.get("layer", "0")) != "text"
            or int(entity.dxf.get("color", 256)) not in {7, 256}
            or _value(entity, "true_color", None) is not None
            or str(entity.dxf.get("linetype", "BYLAYER")).upper() not in {"BYLAYER", "CONTINUOUS"}
            or int(entity.dxf.get("lineweight", -1)) != -3
        ):
            return "native template text display binding drift"
    elif _value(entity, "true_color", None) is not None:
        return "true-color entities are outside the controlled display profile"
    if _value(entity, "transparency", None) is not None:
        return "entity transparency is outside the controlled display profile"
    if any(
        abs(float(component) - expected) > 1e-9
        for component, expected in zip(extrusion, (0.0, 0.0, 1.0))
    ):
        return "non-default OCS/extrusion is outside the controlled display profile"
    if abs(float(_value(entity, "thickness", 0.0))) > 1e-9:
        return "entity thickness is outside the controlled display profile"
    if abs(float(_value(entity, "ltscale", 1.0)) - 1.0) > 1e-9:
        return "entity linetype scale is outside the controlled display profile"
    if str(_value(entity, "material_handle", "0")) != "0":
        return "entity material is outside the controlled display profile"
    if str(_value(entity, "plotstyle_handle", "0")) != "0":
        return "entity plot style is outside the controlled display profile"
    if int(_value(entity, "shadow_mode", 0)) != 0:
        return "entity shadow mode is outside the controlled display profile"
    if str(_value(entity, "visualstyle_handle", "0")) != "0":
        return "entity visual style is outside the controlled display profile"
    if entity.dxftype() == "MTEXT" and int(_value(entity, "bg_fill", 0)) != 0:
        return "MTEXT background fill is outside the controlled display profile"

    color = int(entity.dxf.get("color", 256))
    linetype = str(entity.dxf.get("linetype", "BYLAYER"))
    lineweight = int(entity.dxf.get("lineweight", -1))
    layer = str(entity.dxf.get("layer", "0"))
    if top_level:
        if native_frame or native_text:
            return None
        if color != 256 or linetype != "BYLAYER" or lineweight != -1:
            return "top-level BYLAYER display binding drift"
        if layer not in {"HEATER", "HEATER_LEAD", "DIMENSION"}:
            return "top-level controlled layer binding drift"
    if dimension_cache:
        expected_layer = "0" if entity.dxftype() in {"LINE", "SOLID"} else "DIMENSION"
        expected_linetype = "BYBLOCK" if block_child else "BYLAYER"
        accepted_linetypes = {expected_linetype}
        if entity.dxftype() == "LINE" and not block_child:
            # An explicitly controlled Continuous DIMSTYLE/override regenerates
            # direct dimension lines as Continuous instead of BYLAYER.  The
            # source and the Continuous table definition are validated before
            # the cache reaches this display-binding check.
            accepted_linetypes.add("CONTINUOUS")
        if (
            color != 0
            or layer != expected_layer
            or linetype.upper() not in accepted_linetypes
            or lineweight != -1
        ):
            return "dimension cache BYBLOCK/BYLAYER display binding drift"
    return None
