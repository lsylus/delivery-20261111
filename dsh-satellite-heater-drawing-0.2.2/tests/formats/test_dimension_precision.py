from __future__ import annotations

import copy
import json
from pathlib import Path

import ezdxf
import pytest

from heater_drawing.drawing.dxf_writer import write_page_dxf
from heater_drawing.drawing.readback import (
    ReadbackError,
    _controlled_dimension_text,
    inspect_dxf,
)
from heater_drawing.drawing.sample import _plan_page
from heater_drawing.drawing.template import load_template


ROOT = Path(__file__).resolve().parents[2]


def _precision_dxf(tmp_path: Path, width: str, length: str):
    template = load_template(ROOT / "templates/heater-a4-v1")
    source = json.loads(
        (ROOT / "fixtures/synthetic/heater_sample.json").read_text(encoding="utf-8")
    )["rows"][0]
    row = copy.deepcopy(source)
    row["fields"].update(
        code="PRECISION-CHECK",
        width_mm=width,
        length_mm=length,
        requested_scale="1:2",
        lead_side="long",
    )
    page = _plan_page(
        row, template["layout"], "a" * 64, template["template_sha256"]
    )
    path = tmp_path / f"precision-{width}-{length}.dxf"
    write_page_dxf(path, page, template["layout"], template["fonts"])
    return path, page, template


@pytest.mark.parametrize(
    "value, expected",
    [
        (12.123456000000004, "12.123456"),
        (37.98765400000002, "37.987654"),
        (12.12345649, "12.123456"),
        (37.98765451, "37.987655"),
        (12.120000, "12.12"),
        (0.00000049, "0"),
    ],
)
def test_controlled_dimension_text_uses_six_decimal_places(value, expected):
    assert _controlled_dimension_text(value) == expected


@pytest.mark.parametrize(
    "width,length,expected",
    [
        ("12.123456", "37.987654", ["12.123456", "37.987654"]),
        ("12.12345649", "37.98765451", ["12.123456", "37.987655"]),
        ("12.120000", "37.500000", ["12.12", "37.5"]),
    ],
)
def test_real_precision_dxf_passes_readback(tmp_path, width, length, expected):
    path, page, template = _precision_dxf(tmp_path, width, length)
    result = inspect_dxf(path, [page], template["layout"], template["fonts"])
    assert result["status"] == "passed"
    document = ezdxf.readfile(path)
    actual = [
        text.dxf.text
        for dimension in document.modelspace().query("DIMENSION")
        for text in dimension.virtual_entities()
        if text.dxftype() == "MTEXT"
    ]
    assert actual == expected


@pytest.mark.parametrize(
    "mode,error",
    [
        ("cache-text", "cached display text drift"),
        ("cache-position", "cached display position drift"),
        ("arrow-scale", "arrow geometry drift"),
        ("font-width", "HEATER_CJK effective display properties drift"),
        ("line-color", "cache semantics drift"),
        ("parent-display", "display properties drift"),
    ],
)
def test_precision_dxf_still_rejects_cache_and_display_tampering(
    tmp_path, mode, error
):
    path, page, template = _precision_dxf(tmp_path, "12.123456", "37.987654")
    document = ezdxf.readfile(path)
    dimension = next(iter(document.modelspace().query("DIMENSION")))
    cache = document.blocks[dimension.dxf.geometry]
    if mode == "cache-text":
        next(iter(cache.query("MTEXT"))).text = "12.1235"
    elif mode == "cache-position":
        text = next(iter(cache.query("MTEXT")))
        text.dxf.insert = text.dxf.insert + (3, 0, 0)
    elif mode == "arrow-scale":
        next(iter(cache.query("INSERT"))).dxf.xscale = 3
    elif mode == "font-width":
        document.styles.get("HEATER_CJK").dxf.width = 2
    elif mode == "line-color":
        next(iter(cache.query("LINE"))).dxf.color = 1
    elif mode == "parent-display":
        dimension.dxf.color = 2
    document.saveas(path)
    with pytest.raises(ReadbackError, match=error):
        inspect_dxf(path, [page], template["layout"], template["fonts"])
