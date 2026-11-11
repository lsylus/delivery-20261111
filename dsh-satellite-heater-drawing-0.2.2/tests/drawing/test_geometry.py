from __future__ import annotations

from decimal import Decimal

from heater_drawing.drawing.geometry import build_geometry


def _xy(point):
    return Decimal(point.x), Decimal(point.y)


def test_three_lead_orientations(real_rows, controlled_template):
    _, rows = real_rows
    layout = controlled_template["layout"]
    square = build_geometry(rows[0], Decimal("1"), layout)
    long_side = build_geometry(rows[1], Decimal("1"), layout)
    short_side = build_geometry(rows[2], Decimal("2"), layout)
    square_top = Decimal(square.rectangle.origin.y) + Decimal(square.rectangle.length_mm)
    short_top = Decimal(short_side.rectangle.origin.y) + Decimal(short_side.rectangle.length_mm)
    assert all(
        _xy(segment.start)[1] < square_top < _xy(segment.end)[1]
        for segment in square.lead_segments
    )
    assert all(
        _xy(segment.start)[0] < Decimal(long_side.rectangle.origin.x) < _xy(segment.end)[0]
        for segment in long_side.lead_segments
    )
    assert all(
        _xy(segment.start)[1] < short_top < _xy(segment.end)[1]
        for segment in short_side.lead_segments
    )


def test_scale_never_changes_true_geometry(real_rows, controlled_template):
    row = real_rows[1][2]
    one = build_geometry(row, Decimal("1"), controlled_template["layout"])
    five = build_geometry(row, Decimal("5"), controlled_template["layout"])
    assert one.rectangle.width_mm == five.rectangle.width_mm == "100"
    assert one.rectangle.length_mm == five.rectangle.length_mm == "300"
    assert [item.value_mm for item in five.dimension_definitions] == ["100", "300"]


def test_short_edge_rule_is_paper_based(real_rows, controlled_template):
    row = real_rows[1][2]
    geometry = build_geometry(row, Decimal("2"), controlled_template["layout"])
    starts = sorted(Decimal(item.start.x) for item in geometry.lead_segments)
    assert (starts[1] - starts[0]) / Decimal("2") == Decimal("12")
