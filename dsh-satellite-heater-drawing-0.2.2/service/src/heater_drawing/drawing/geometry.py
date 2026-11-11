"""True-size heater geometry for one controlled drawing page."""

from __future__ import annotations

from decimal import Decimal

from heater_drawing.domain.models import (
    DimensionDefinition,
    Geometry,
    HeaterRow,
    LeadSegment,
    Point,
    RectangleGeometry,
)

from .leads import lead_parameters


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def point(x: Decimal, y: Decimal) -> Point:
    return Point(x=decimal_text(x), y=decimal_text(y))


def build_geometry(row: HeaterRow, denominator: Decimal, layout: dict) -> Geometry:
    """Build model-space geometry in real millimetres; scale only chooses paper placement."""

    values = row.values
    width = Decimal(values.width_mm)
    length = Decimal(values.length_mm)
    center_profile = layout["heater_center_paper_mm"]
    center = center_profile.get("sample_overrides", {}).get(
        values.code, center_profile["fallback"]
    )
    center_x = Decimal(str(center["x"])) * denominator
    center_y = Decimal(str(center["y"])) * denominator
    left = center_x - width / 2
    bottom = center_y - length / 2
    top = bottom + length
    lead = lead_parameters(
        width, length, denominator, layout["lead_parameters_paper_mm"]
    )
    gap = lead["center_gap"] * denominator
    inside = lead["inside_length"] * denominator
    outside = lead["outside_length"] * denominator

    if values.lead_side.value == "long" and width != length:
        segments = [
            LeadSegment(
                start=point(left - outside, center_y + delta),
                end=point(left + inside, center_y + delta),
            )
            for delta in (-gap / 2, gap / 2)
        ]
    else:
        segments = [
            LeadSegment(
                start=point(center_x + delta, top - inside),
                end=point(center_x + delta, top + outside),
            )
            for delta in (-gap / 2, gap / 2)
        ]

    return Geometry(
        rectangle=RectangleGeometry(
            origin=point(left, bottom),
            width_mm=values.width_mm,
            length_mm=values.length_mm,
        ),
        lead_segments=segments,
        dimension_definitions=[
            DimensionDefinition(measurement="width", value_mm=values.width_mm),
            DimensionDefinition(measurement="length", value_mm=values.length_mm),
        ],
    )
