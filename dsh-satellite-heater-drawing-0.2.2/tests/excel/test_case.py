from __future__ import annotations

import hashlib
import json
from pathlib import Path
from copy import copy
import subprocess
import sys

from heater_drawing.excel import parse_workbook, validate_rows


ROOT = Path(__file__).resolve().parents[2]


def test_real_case_matches_expected_and_preserves_source() -> None:
    source = ROOT / "fixtures/case/加热器图纸.xlsx"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    expected = json.loads(
        (ROOT / "fixtures/case/expected.json").read_text(encoding="utf-8")
    )

    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows)

    assert not parsed.has_errors
    assert not validated.has_errors
    assert [row.source.excel_row for row in parsed.rows] == [2, 3, 4]
    actual = [
        {"excel_row": row.source.excel_row, **row.values.model_dump(mode="json")}
        for row in validated.rows
    ]
    assert actual == expected["rows"]
    assert actual[1]["standards_reviewer"] == "郑玲"
    assert [item["quantity_text"] for item in actual] == [
        "18片",
        "12（备份2）",
        "76片（备份13片）",
    ]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_reordered_headers_and_allowed_header_normalization(tmp_path: Path) -> None:
    from heater_drawing.excel.headers import FIELD_ORDER, headers_in_order
    from tests.excel.helpers import VALID_VALUES, make_workbook

    headers = headers_in_order()
    headers[2] = "  加热器宽度\r\n(mm)  "
    order = list(reversed(range(len(headers))))
    source = make_workbook(
        tmp_path / "reordered.xlsx",
        headers=[headers[index] for index in order],
        rows=[[VALID_VALUES[FIELD_ORDER[index]] for index in order]],
    )
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows)
    assert not parsed.has_errors
    assert not validated.has_errors
    assert validated.rows[0].values.width_mm == "25"


def test_formatted_empty_tail_does_not_create_records(tmp_path: Path) -> None:
    from openpyxl import load_workbook
    from tests.excel.helpers import make_workbook

    source = make_workbook(tmp_path / "formatted-tail.xlsx")
    workbook = load_workbook(source)
    sheet = workbook["Sheet1"]
    sheet["A500"].number_format = "0.00"
    sheet["Q500"].fill = copy(sheet["A1"].fill)
    workbook.save(source)
    workbook.close()
    assert [row.source.excel_row for row in parse_workbook(source).rows] == [2]


def test_check_excel_cli_emits_expected_case_report(tmp_path: Path) -> None:
    output = tmp_path / "case.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_excel.py"),
            "--input",
            str(ROOT / "fixtures/case/加热器图纸.xlsx"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    expected = json.loads(
        (ROOT / "fixtures/case/expected.json").read_text(encoding="utf-8")
    )
    assert result.returncode == 0
    assert payload["status"] == "valid"
    assert payload["rows"] == expected["rows"]
    assert payload["outputs"] == []
