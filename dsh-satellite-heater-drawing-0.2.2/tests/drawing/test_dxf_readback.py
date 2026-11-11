from __future__ import annotations

from copy import deepcopy

import pytest

from heater_drawing.drawing.dxf_writer import export_planned_dxf
from heater_drawing.drawing.readback import ReadbackError, inspect_dxf


def test_combined_dxf_readback_preserves_editable_engineering_semantics(
    tmp_path, real_plan, real_revision, controlled_template
):
    output = tmp_path / "combined.dxf"
    export_planned_dxf(output, real_plan, real_revision, controlled_template)
    report = inspect_dxf(
        output, list(real_plan.pages), controlled_template["layout"], controlled_template["fonts"]
    )
    assert report["status"] == "passed"
    assert report["insunits"] == 4 and report["unit"] == "mm"
    assert report["native_dimension_entities"] == 6
    assert report["editable_text_entities"] > 0
    assert [item["geometry_mm"] for item in report["pages"]] == [
        {"width": 25.0, "length": 25.0},
        {"width": 30.0, "length": 50.0},
        {"width": 100.0, "length": 300.0},
    ]
    assert [item["scale"] for item in report["pages"]] == ["1:1", "1:1", "1:2"]


def test_exact_geometry_bbox_boundary_passes_and_point_one_one_mm_overflow_fails(
    tmp_path, real_plan, controlled_template
):
    page = real_plan.pages[0]
    output = tmp_path / "boundary.dxf"
    from heater_drawing.drawing.dxf_writer import write_page_dxf

    write_page_dxf(
        output, page, controlled_template["layout"], controlled_template["fonts"],
        template_path=controlled_template["directory"] / "template.dxf",
    )
    baseline = inspect_dxf(
        output, [page], controlled_template["layout"], controlled_template["fonts"]
    )
    box = baseline["pages"][0]["geometry_lead_dimension_box_paper_mm"]
    exact = deepcopy(controlled_template["layout"])
    exact["drawing_area_mm"] = dict(zip(("left", "bottom", "right", "top"), box, strict=True))
    assert inspect_dxf(output, [page], exact, controlled_template["fonts"])["status"] == "passed"

    outside = deepcopy(exact)
    outside["drawing_area_mm"]["right"] -= 0.11
    with pytest.raises(ReadbackError, match="leave drawing area"):
        inspect_dxf(output, [page], outside, controlled_template["fonts"])
