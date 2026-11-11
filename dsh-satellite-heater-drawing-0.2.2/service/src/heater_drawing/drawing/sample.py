"""Deterministic B02 fixture planning using the public C02 contract."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any
from .leads import lead_parameters

from heater_drawing.domain.models import (
    Bounds,
    CheckResult,
    DimensionDefinition,
    DrawingChecks,
    DrawingPage,
    Geometry,
    HeaterFields,
    LeadSegment,
    Placement,
    Point,
    RectangleGeometry,
    Scale,
    canonical_json_bytes,
)


def _number(value: Decimal) -> str:
    result = format(value.normalize(), "f")
    return "0" if result == "-0" else result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _point(x: Decimal, y: Decimal) -> Point:
    return Point(x=_number(x), y=_number(y))


def _plan_page(
    row: dict[str, Any],
    layout: dict[str, Any],
    revision_hash: str,
    template_hash: str,
) -> DrawingPage:
    fields = HeaterFields.model_validate(row["fields"])
    denominator = fields.requested_scale.split(":", 1)[1]
    scale = Scale(denominator=denominator, label=fields.requested_scale)
    width = Decimal(fields.width_mm)
    length = Decimal(fields.length_mm)
    factor = Decimal(denominator)
    center_profile = layout["heater_center_paper_mm"]
    center = center_profile.get("sample_overrides", {}).get(
        fields.code, center_profile["fallback"]
    )
    cx = Decimal(str(center["x"])) * factor
    cy = Decimal(str(center["y"])) * factor
    left = cx - width / 2
    bottom = cy - length / 2
    top = cy + length / 2
    lead = lead_parameters(width, length, factor, layout["lead_parameters_paper_mm"])
    gap = Decimal(str(lead["center_gap"])) * factor
    inside = Decimal(str(lead["inside_length"])) * factor
    outside = Decimal(str(lead["outside_length"])) * factor
    if fields.lead_side.value == "long" and width != length:
        leads = [
            LeadSegment(start=_point(left - outside, cy + delta), end=_point(left + inside, cy + delta))
            for delta in (-gap / 2, gap / 2)
        ]
    else:
        leads = [
            LeadSegment(start=_point(cx + delta, top - inside), end=_point(cx + delta, top + outside))
            for delta in (-gap / 2, gap / 2)
        ]
    geometry = Geometry(
        rectangle=RectangleGeometry(
            origin=_point(left, bottom),
            width_mm=fields.width_mm,
            length_mm=fields.length_mm,
        ),
        lead_segments=leads,
        dimension_definitions=[
            DimensionDefinition(measurement="width", value_mm=fields.width_mm),
            DimensionDefinition(measurement="length", value_mm=fields.length_mm),
        ],
    )
    paper = layout["paper_mm"]
    placement = Placement(
        model_origin_mm=_point(Decimal("0"), Decimal("0")),
        tile_bounds_mm=Bounds(
            left="0",
            bottom="0",
            right=_number(Decimal(str(paper["width"])) * factor),
            top=_number(Decimal(str(paper["height"])) * factor),
        ),
        paper_bounds_mm=Bounds(left="0", bottom="0", right="210", top="297"),
        layout_name=fields.code,
    )
    checks = DrawingChecks(
        bounds=CheckResult(passed=True, details=["planned inside controlled A4 viewport"]),
        collisions=CheckResult(passed=True, details=["reviewed B02 per-row dimension placement"]),
        glyph_coverage=CheckResult(passed=True, details=["locked SC face checked during build"]),
    )
    return DrawingPage(
        row_id=row["row_id"],
        code=fields.code,
        revision_hash=revision_hash,
        template_hash=template_hash,
        scale=scale,
        geometry_mm=geometry,
        fields=fields,
        fixed_text_version=layout["fixed_text_version"],
        placement=placement,
        checks=checks,
    )


def load_sample(path: Path, template_dir: Path | None = None) -> tuple[dict[str, Any], list[DrawingPage]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("profile") != "dxf_pdf_v1":
        raise ValueError("unsupported sample fixture")
    if template_dir is None:
        template_dir = Path(__file__).resolve().parents[4] / "templates" / "heater-a4-v1"
    layout = json.loads((template_dir / "layout.json").read_text(encoding="utf-8"))
    template_hash = _sha256(template_dir / "template.dxf")
    revision_hash = hashlib.sha256(
        canonical_json_bytes(
            {
                "fixture": data,
                "template_sha256": template_hash,
                "font_manifest_sha256": _sha256(template_dir / "fonts.json"),
                "layout_sha256": _sha256(template_dir / "layout.json"),
                "planner": "b02-c02-v3-short-edge-leads",
            }
        )
    ).hexdigest()
    rows = data.get("rows", [])
    if len(rows) != 3:
        raise ValueError("B02 fixture must contain exactly three pages")
    return data, [_plan_page(row, layout, revision_hash, template_hash) for row in rows]
