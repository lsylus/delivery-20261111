#!/usr/bin/env python3
"""Rebuild the small, reviewable B03 invalid workbook fixtures."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from heater_drawing.excel.headers import FIELD_ORDER, headers_in_order


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures" / "invalid"
VALID = {
    "name": "测试加热器",
    "code": "HX-01",
    "width_mm": 25,
    "length_mm": 50,
    "lead_side": "短边",
    "resistance_ohm": 20,
    "tolerance_ohm": 1,
    "quantity_text": "12（备份2）",
    "requested_scale": "1:2",
    "organization": "测试单位",
    "model": "HX",
    "designer": "设计甲",
    "checker": "校对乙",
    "reviewer": "审核丙",
    "standards_reviewer": "标审丁",
    "approver": "批准戊",
    "stage": "Z",
}


def save(name: str, rows: list[dict[str, object]], *, formula: bool = False) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(headers_in_order())
    for values in rows:
        sheet.append([values.get(field) for field in FIELD_ORDER])
    if formula:
        sheet["C2"] = "=10+15"
    workbook.save(OUTPUT / name)
    workbook.close()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    invalid = dict(VALID)
    invalid.update(
        {
            "code": "../BAD",
            "width_mm": 60,
            "lead_side": "右边",
            "tolerance_ohm": -1,
            "requested_scale": "1:0",
            "designer": None,
        }
    )
    save("invalid-values.xlsx", [VALID, invalid])

    duplicate = dict(VALID)
    duplicate["code"] = "hx-01"
    duplicate["name"] = "重复代号加热器"
    save("duplicate-code.xlsx", [VALID, duplicate])
    save("formula.xlsx", [VALID], formula=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
