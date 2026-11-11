"""Versioned B02 format profile."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatProfile:
    name: str
    dxf_version: str
    dxf_acad_version: str
    insunits: int
    unit: str
    paper_width_mm: float
    paper_height_mm: float
    dimension_tolerance_mm: float
    paper_tolerance_mm: float


DXF_PDF_PROFILE = FormatProfile(
    name="dxf_pdf_v1",
    dxf_version="R2018",
    dxf_acad_version="AC1032",
    insunits=4,
    unit="mm",
    paper_width_mm=210.0,
    paper_height_mm=297.0,
    dimension_tolerance_mm=1e-6,
    paper_tolerance_mm=0.1,
)


# Values that affect the visible cache generated for native linear dimensions.
# Keep these explicit so a later DIMENSION.render() does not inherit library defaults.
CONTROLLED_DIMSTYLE_VALUES = {
    "dimgap": 0.625,
    "dimexe": 0.0,
    "dimexo": 0.0,
    "dimtad": 0,
    "dimtih": 0,
    "dimtoh": 0,
    "dimtix": 0,
    "dimtofl": 1,
    "dimsah": 0,
    "dimtsz": 0.0,
    "dimse1": 0,
    "dimse2": 0,
    "dimsoxd": 0,
    "dimclrd": 0,
    "dimclre": 0,
    "dimclrt": 0,
    "dimzin": 8,
    "dimdec": 6,
    # ezdxf treats an explicit zero DIMRND as integer rounding; use the
    # supported precision explicitly, including fractional millimetres.
    "dimrnd": 0.000001,
    "dimdsep": 46,
}

CONTROLLED_DIMENSION_OVERRIDES = {
    "dimlfac": 1.0,
    "dimtxt": 3.5,
    "dimasz": 2.5,
}


NATIVE_PROFILE = "dwg_pdf_v1"


def output_template(template: dict, profile: str) -> dict:
    """Derive the versioned output style after the source template hash is verified.

    The source DXF/font manifests remain immutable. Native dimensions use the
    engineer's single-line TXT style; Noto remains the conservative metric face.
    """
    if profile != NATIVE_PROFILE:
        return template
    if template.get("output_style_profile") == NATIVE_PROFILE:
        return template
    from copy import deepcopy
    result = deepcopy(template)
    result["output_style_profile"] = NATIVE_PROFILE
    result["fonts"].update({
        "dimension_cad_font_file": "txt.shx",
        "dimension_style_width_factor": 0.85,
        "dimension_overrides": {"dimtxt": 5.0, "dimasz": 2.5},
        "dimension_style_values": {"dimexo": 0.625, "dimexe": 1.25, "dimtad": 1},
        "dimension_overrides_by_code": {"KX-11-WR-100-300-M1": {"dimasz": 2.0}},
        "native_hz_technical_metrics": True,
        "native_template_directory": str(template["directory"]),
    })
    # The old Noto PDF substitute required this translation and extra wrapping.
    # Native HZ can retain the engineer's original technical block geometry.
    dx, dy = result["layout"]["development_baseline"]["technical_block_translation_paper_mm"]
    technical = result["layout"]["technical_text"]
    technical["point_mm"] = [technical["point_mm"][0] - dx, technical["point_mm"][1] - dy]
    technical["bounds_mm"] = [value - (dx if index % 2 == 0 else dy)
                              for index, value in enumerate(technical["bounds_mm"])]
    technical["line_policy"] = "sample_original_eight_v1"
    for name in ("technical_text_bbox_mm",):
        bounds = result["layout"][name]
        for side in ("left", "right"):
            bounds[side] -= dx
        for side in ("top", "bottom"):
            bounds[side] -= dy
    for bounds in result["layout"]["forbidden_zones_mm"]:
        if bounds["name"] == "technical-requirements":
            for side in ("left", "right"):
                bounds[side] -= dx
            for side in ("top", "bottom"):
                bounds[side] -= dy
    # The built-in TXT substitute advances ASCII spaces as full-width glyphs
    # in HZ TEXT. Keep spaced fixed labels editable and place glyphs using
    # the source's half-width ASCII-space advances, avoiding clipping/overlap.
    import re
    extra = []
    for index, record in enumerate(result["layout"]["fixed_text"]):
        text = record["text"]
        if record["entity_type"] != "TEXT" or " " not in text or not re.fullmatch(r"[\u3400-\u9fff ]+", text):
            continue
        advance = record["height_mm"] * record["width_factor"]
        cursor = 0.0
        first = True
        for char in text:
            if char == " ":
                cursor += advance / 2
                continue
            if first:
                record["text"] = char
                first = False
            else:
                glyph = deepcopy(record)
                glyph["text"] = char
                glyph["point_mm"][0] += cursor
                glyph["native_source_fixed_id"] = str(index)
                if char == "页":
                    glyph["allowed_frame_crossings"] = [36]
                extra.append(glyph)
            cursor += advance
    result["layout"]["fixed_text"].extend(extra)
    return result


def dimension_overrides(fonts: dict, code: str = "") -> dict:
    return {**CONTROLLED_DIMENSION_OVERRIDES,
            **fonts.get("dimension_overrides", {}),
            **fonts.get("dimension_overrides_by_code", {}).get(code, {})}


def dimension_style_values(fonts: dict) -> dict:
    return {**CONTROLLED_DIMSTYLE_VALUES, **fonts.get("dimension_style_values", {})}


# Native DIMENSION regeneration can obtain each visible line type from either
# HEATER_DIM or an entity-level override.  An omitted value is the ezdxf
# default and is equivalent to the controlled Continuous result.
CONTROLLED_DIMENSION_LINETYPE_FIELDS = (
    "dimltype",
    "dimltex1",
    "dimltex2",
)
