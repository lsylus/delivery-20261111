from __future__ import annotations

import hashlib
from pathlib import Path

from openpyxl import load_workbook

from heater_drawing.excel import parse_workbook, validate_rows, write_actual_workbook
from tests.excel.helpers import imported_row


def test_actual_workbook_preserves_text_and_forces_formula_style_text(tmp_path: Path) -> None:
    row = imported_row(
        changes={
            "name": "=CMD|' /C calc'!A0",
            "quantity_text": "+12（备份2）",
            "code": "@HX-01",
            "width_mm": "25.000",
            "length_mm": "50.5000",
        }
    )
    validated = validate_rows([row])
    assert not validated.has_errors
    output = write_actual_workbook(tmp_path / "actual.xlsx", validated.rows)

    workbook = load_workbook(output, data_only=False)
    sheet = workbook["Sheet1"]
    assert sheet["A2"].value == "=CMD|' /C calc'!A0"
    assert sheet["A2"].data_type == "s"
    assert sheet["B2"].value == "@HX-01"
    assert sheet["B2"].data_type == "s"
    assert sheet["H2"].value == "+12（备份2）"
    assert sheet["H2"].data_type == "s"
    assert sheet["C2"].value == 25
    assert sheet["D2"].value == 50.5
    assert all(
        sheet.cell(2, column).data_type != "f" for column in range(1, 18)
    )
    workbook.close()


def test_real_case_roundtrip_does_not_change_source_or_add_fields(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "fixtures/case/加热器图纸.xlsx"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows)
    output = write_actual_workbook(tmp_path / "actual-case.xlsx", validated.rows)
    reparsed = parse_workbook(output)
    revalidated = validate_rows(reparsed.rows)
    assert not reparsed.has_errors
    assert not revalidated.has_errors
    assert len(revalidated.rows) == 3
    assert revalidated.rows[1].raw.quantity_text == "12（备份2）"
    assert revalidated.rows[1].raw.standards_reviewer == "郑玲"
    assert set(revalidated.rows[0].raw.model_dump()) == set(parsed.rows[0].raw.model_dump())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
