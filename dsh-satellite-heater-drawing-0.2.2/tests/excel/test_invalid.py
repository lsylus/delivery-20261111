from __future__ import annotations

from decimal import Decimal
import math
from pathlib import Path
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import load_workbook

from heater_drawing.domain.models import ErrorCode, Severity
from heater_drawing.excel import parse_workbook, validate_rows
from heater_drawing.excel.headers import FIELD_ORDER, headers_in_order
from tests.excel.helpers import VALID_VALUES, imported_row, make_workbook, values_list


def errors(result: object) -> list[object]:
    return [issue for issue in result.issues if issue.severity == Severity.ERROR]


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
def test_header_failures_are_workbook_issues(tmp_path: Path, mode: str) -> None:
    headers = headers_in_order()
    row = values_list()
    if mode == "missing":
        headers.pop(5)
        row.pop(5)
    elif mode == "duplicate":
        headers[5] = headers[4]
    else:
        headers.append("任意新字段")
        row.append("value")
    parsed = parse_workbook(
        make_workbook(tmp_path / f"{mode}.xlsx", headers=headers, rows=[row])
    )
    assert errors(parsed)
    assert all(issue.scope.value == "workbook" for issue in errors(parsed))
    assert any(issue.raw_value is not None or issue.field is not None for issue in errors(parsed))


def test_unnamed_column_with_business_value_is_not_silently_ignored(tmp_path: Path) -> None:
    headers = [*headers_in_order(), None]
    row = [*values_list(), "orphan value"]
    parsed = parse_workbook(
        make_workbook(tmp_path / "unnamed.xlsx", headers=headers, rows=[row])
    )
    issue = next(issue for issue in parsed.issues if "未命名列" in issue.message)
    assert issue.scope.value == "workbook"
    assert issue.raw_value == "Sheet1!R1"


def test_partial_row_is_retained_and_all_missing_fields_are_reported(tmp_path: Path) -> None:
    row = [None] * 17
    row[1] = "PARTIAL-01"
    parsed = parse_workbook(
        make_workbook(tmp_path / "partial.xlsx", rows=[values_list(), row])
    )
    validated = validate_rows(parsed.rows)
    assert [item.source.excel_row for item in parsed.rows] == [2, 3]
    row_three = [issue for issue in validated.issues if issue.excel_row == 3]
    assert len(row_three) == 16
    assert {issue.error_code for issue in row_three} == {ErrorCode.MISSING_FIELD}


def test_formula_is_rejected_without_using_cached_value(tmp_path: Path) -> None:
    source = make_workbook(tmp_path / "formula.xlsx")
    workbook = load_workbook(source)
    sheet = workbook["Sheet1"]
    sheet["C2"] = "=10+15"
    workbook.save(source)
    workbook.close()
    parsed = parse_workbook(source)
    formula = [issue for issue in parsed.issues if issue.field == "width_mm"]
    assert len(formula) == 1
    assert formula[0].error_code == ErrorCode.UNSUPPORTED_INPUT
    assert formula[0].raw_value == "=10+15"
    assert parsed.rows[0].raw.width_mm == "=10+15"


def test_formula_cached_value_is_never_read(tmp_path: Path) -> None:
    source = make_workbook(tmp_path / "formula-cache.xlsx")
    workbook = load_workbook(source)
    workbook["Sheet1"]["C2"] = "=10+15"
    workbook.save(source)
    workbook.close()

    input_buffer = BytesIO(source.read_bytes())
    output_buffer = BytesIO()
    with ZipFile(input_buffer) as original, ZipFile(
        output_buffer, "w", compression=ZIP_DEFLATED
    ) as rewritten:
        for info in original.infolist():
            data = original.read(info)
            if info.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b"<f>10+15</f><v></v>", b"<f>10+15</f><v>999</v>")
            rewritten.writestr(info, data)
    source.write_bytes(output_buffer.getvalue())

    parsed = parse_workbook(source)
    assert parsed.rows[0].raw.width_mm == "=10+15"
    issue = next(issue for issue in parsed.issues if issue.field == "width_mm")
    assert issue.raw_value == "=10+15"


def test_merged_business_cell_is_non_skippable_workbook_error(tmp_path: Path) -> None:
    source = make_workbook(tmp_path / "merged.xlsx")
    workbook = load_workbook(source)
    workbook["Sheet1"].merge_cells("A2:B2")
    workbook.save(source)
    workbook.close()
    parsed = parse_workbook(source)
    issue = next(issue for issue in parsed.issues if "合并单元格" in issue.message)
    assert issue.scope.value == "workbook"
    assert not issue.skippable


def test_nonempty_other_sheet_is_warning_only(tmp_path: Path) -> None:
    parsed = parse_workbook(
        make_workbook(tmp_path / "multiple.xlsx", extra_sheet=True)
    )
    assert not parsed.has_errors
    assert len(parsed.issues) == 1
    assert parsed.issues[0].severity == Severity.WARNING
    assert "未处理" in parsed.issues[0].message


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"name": ""}, "name"),
        ({"designer": 0}, "designer"),
        ({"width_mm": True}, "width_mm"),
        ({"width_mm": float("nan")}, "width_mm"),
        ({"width_mm": float("inf")}, "width_mm"),
        ({"width_mm": "1e3"}, "width_mm"),
        ({"width_mm": "０.5"}, "width_mm"),
        ({"width_mm": 0}, "width_mm"),
        ({"width_mm": -1}, "width_mm"),
        ({"width_mm": 51}, "width_mm"),
        ({"lead_side": "右边"}, "lead_side"),
        ({"tolerance_ohm": -1}, "tolerance_ohm"),
        ({"tolerance_ohm": 21}, "tolerance_ohm"),
        ({"requested_scale": "0:1"}, "requested_scale"),
        ({"requested_scale": "1:0"}, "requested_scale"),
        ({"requested_scale": "2:1"}, "requested_scale"),
        ({"requested_scale": "1:0.5"}, "requested_scale"),
    ],
)
def test_field_validation_boundaries(changes: dict[str, object], field: str) -> None:
    result = validate_rows([imported_row(changes=changes)])
    assert any(issue.field == field for issue in result.issues)
    retained = result.source_rows[0].raw.model_dump()[field]
    if isinstance(changes[field], float) and math.isnan(changes[field]):
        assert math.isnan(retained)
    else:
        assert retained == changes[field]


def test_decimal_values_outside_exact_xlsx_precision_are_rejected() -> None:
    row = imported_row(
        changes={
            "width_mm": Decimal("12.123456789012345678"),
            "length_mm": Decimal("37.987654321098765432"),
            "resistance_ohm": Decimal("58.800000000000000001"),
            "tolerance_ohm": Decimal("1.760000000000000001"),
        }
    )
    result = validate_rows([row])
    assert result.has_errors
    assert result.rows == ()
    assert {issue.field for issue in result.issues} == {
        "width_mm",
        "length_mm",
        "resistance_ohm",
        "tolerance_ohm",
    }


@pytest.mark.parametrize(
    "code",
    [
        "../HX",
        "A/B",
        "A\\B",
        "A:B",
        "CON",
        "con.txt",
        "COM¹",
        "LPT².doc",
        "com³.TXT",
        "HX.",
        "HX ",
        "HX\x00X",
        "HX\u0085X",
        "A" * 256,
    ],
)
def test_unsafe_cross_platform_codes_are_rejected(code: str) -> None:
    result = validate_rows([imported_row(changes={"code": code})])
    assert any(issue.field == "code" for issue in result.issues)


def test_duplicate_codes_mark_every_related_row_case_insensitively() -> None:
    rows = [
        imported_row(excel_row=2, changes={"code": "HX-Abc"}),
        imported_row(excel_row=3, changes={"code": "hx-aBC"}),
        imported_row(excel_row=4, changes={"code": "OTHER"}),
    ]
    result = validate_rows(rows)
    duplicates = [
        issue for issue in result.issues if issue.error_code == ErrorCode.DUPLICATE_CODE
    ]
    assert [issue.excel_row for issue in duplicates] == [2, 3]
    assert all("2, 3" in issue.message for issue in duplicates)


def test_literal_formula_style_text_is_not_mistaken_for_excel_formula(tmp_path: Path) -> None:
    values = dict(VALID_VALUES)
    values["name"] = "=not-a-formula"
    parsed = parse_workbook(
        make_workbook(tmp_path / "literal.xlsx", rows=[values_list(values)])
    )
    validated = validate_rows(parsed.rows)
    assert not parsed.has_errors
    assert not validated.has_errors
    assert validated.rows[0].values.name == "=not-a-formula"
