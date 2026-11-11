import pymupdf

from heater_drawing.drawing.native_text_metrics import union_bounds


def test_calibration_square_includes_zero_area_line_bounds():
    edges = [pymupdf.Rect(10, 10, 20, 10), pymupdf.Rect(20, 10, 20, 20),
             pymupdf.Rect(10, 20, 20, 20), pymupdf.Rect(10, 10, 10, 20)]
    assert list(union_bounds(edges)) == [10, 10, 20, 20]
