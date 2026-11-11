from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook

from heater_drawing.domain.models import (
    ImportedHeaterRow,
    RawHeaterFields,
    SourceLocation,
)
from heater_drawing.excel.headers import FIELD_ORDER, headers_in_order


VALID_VALUES: dict[str, Any] = {
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


def values_list(values: dict[str, Any] | None = None) -> list[Any]:
    source = VALID_VALUES if values is None else values
    return [source[field] for field in FIELD_ORDER]


def make_workbook(
    path: Path,
    *,
    headers: Iterable[Any] | None = None,
    rows: Iterable[Iterable[Any]] | None = None,
    extra_sheet: bool = False,
) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(list(headers) if headers is not None else headers_in_order())
    for row in rows if rows is not None else [values_list()]:
        sheet.append(list(row))
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.data_type = "s"
    if extra_sheet:
        workbook.create_sheet("Other")["A1"] = "not imported"
    workbook.save(path)
    workbook.close()
    return path


def imported_row(
    *,
    excel_row: int = 2,
    changes: dict[str, Any] | None = None,
) -> ImportedHeaterRow:
    values = dict(VALID_VALUES)
    values.update(changes or {})
    return ImportedHeaterRow(
        row_id=f"Sheet1:{excel_row}",
        source=SourceLocation(sheet="Sheet1", excel_row=excel_row),
        raw=RawHeaterFields(**values),
    )
