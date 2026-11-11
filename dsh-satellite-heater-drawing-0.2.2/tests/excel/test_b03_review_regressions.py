from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import load_workbook

from heater_drawing.domain.models import ErrorCode
from heater_drawing.excel import (
    WorkbookLimits,
    parse_workbook,
    validate_rows,
    write_actual_workbook,
)
from heater_drawing.excel.numeric import UnsupportedExcelNumeric
from tests.excel.helpers import VALID_VALUES, imported_row, make_workbook, values_list


ROOT = Path(__file__).resolve().parents[2]
REVIEW_LINUX = ROOT / "docs/evidence/B03-review/linux"
REVIEW_FOCUSED = ROOT / "docs/evidence/B03-review/focused"
REVIEW_FIX_1 = ROOT / "docs/evidence/B03-review-fix-1"
REVIEW_FIX_2 = ROOT / "docs/evidence/B03-review-fix-2/checks"
REVIEW_FIX_3 = ROOT / "docs/evidence/B03-review-fix-3/checks"
CONTENT_TYPES_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
SPREADSHEET_NAMESPACE = (
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
)
WORKSHEET_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)
WORKBOOK_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)


def _shared_string_reference_workbook(
    tmp_path: Path,
    name: str,
    index: str | None,
    package_edit: Callable[[dict[str, bytes]], None] | None = None,
) -> Path:
    with ZipFile(ROOT / "fixtures/case/加热器图纸.xlsx") as archive:
        package = {member.filename: archive.read(member) for member in archive.infolist()}
    worksheet = ElementTree.fromstring(package["xl/worksheets/sheet1.xml"])
    cell = next(
        item
        for item in worksheet.iter(f"{{{SPREADSHEET_NAMESPACE}}}c")
        if item.attrib.get("r") == "O3"
    )
    cell.clear()
    cell.attrib.update({"r": "O3", "t": "s"})
    if index is not None:
        ElementTree.SubElement(
            cell, f"{{{SPREADSHEET_NAMESPACE}}}v"
        ).text = index
    package["xl/worksheets/sheet1.xml"] = ElementTree.tostring(worksheet)
    if package_edit is not None:
        package_edit(package)
    output = tmp_path / f"{name}.xlsx"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for member_name, data in package.items():
            archive.writestr(member_name, data)
    return output


def _use_default_worksheet_content_type(package: dict[str, bytes]) -> None:
    content_types = ElementTree.fromstring(package["[Content_Types].xml"])
    for element in list(content_types):
        if element.attrib.get("PartName") == "/xl/worksheets/sheet1.xml":
            content_types.remove(element)
        elif (
            element.tag == f"{{{CONTENT_TYPES_NAMESPACE}}}Default"
            and element.attrib.get("Extension") == "xml"
        ):
            element.set("ContentType", WORKSHEET_CONTENT_TYPE)
    package["[Content_Types].xml"] = ElementTree.tostring(content_types)


def _rename_worksheet(package: dict[str, bytes], target: str) -> None:
    part = "xl/worksheets/heaters.xml"
    content_types = ElementTree.fromstring(package["[Content_Types].xml"])
    for element in content_types:
        if element.attrib.get("PartName") == "/xl/worksheets/sheet1.xml":
            element.set("PartName", f"/{part}")
    package["[Content_Types].xml"] = ElementTree.tostring(content_types)
    relationships = ElementTree.fromstring(package["xl/_rels/workbook.xml.rels"])
    for element in relationships:
        if element.attrib.get("Type", "").endswith("/worksheet"):
            element.set("Target", target)
    package["xl/_rels/workbook.xml.rels"] = ElementTree.tostring(relationships)
    package[part] = package.pop("xl/worksheets/sheet1.xml")


def _add_ambiguous_workbook_part(package: dict[str, bytes]) -> None:
    package["xl/second-workbook.xml"] = package["xl/workbook.xml"]
    package["xl/_rels/second-workbook.xml.rels"] = package[
        "xl/_rels/workbook.xml.rels"
    ]
    content_types = ElementTree.fromstring(package["[Content_Types].xml"])
    ElementTree.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NAMESPACE}}}Override",
        {
            "PartName": "/xl/second-workbook.xml",
            "ContentType": WORKBOOK_CONTENT_TYPE,
        },
    )
    package["[Content_Types].xml"] = ElementTree.tostring(content_types)


def _mismatch_root_workbook_relationship(package: dict[str, bytes]) -> None:
    package["xl/untyped-workbook.xml"] = package["xl/workbook.xml"]
    root_relationships = ElementTree.fromstring(package["_rels/.rels"])
    for element in root_relationships:
        if element.attrib.get("Type", "").endswith("/officeDocument"):
            element.set("Target", "xl/untyped-workbook.xml")
    package["_rels/.rels"] = ElementTree.tostring(root_relationships)


def _run_excel_cli(
    tmp_path: Path, source: Path
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, object], Path]:
    output = tmp_path / f"{source.stem}.json"
    actual = tmp_path / f"{source.stem}-actual.xlsx"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_excel.py"),
            "--input",
            str(source),
            "--output",
            str(output),
            "--actual-output",
            str(actual),
        ],
        cwd=ROOT,
        check=False,
    )
    return process, json.loads(output.read_text(encoding="utf-8")), actual


@pytest.mark.parametrize(
    "value",
    [
        "23.123456789012345678",
        "23.12345678901234",
        "0." + "0" * 324 + "1",
        "9" * 309,
    ],
)
def test_unrepresentable_xlsx_decimals_are_row_issues(value: str) -> None:
    result = validate_rows(
        [imported_row(changes={"resistance_ohm": value, "tolerance_ohm": "0"})]
    )
    assert result.has_errors
    assert result.source_rows[0].raw.resistance_ohm == value
    issue = next(issue for issue in result.issues if issue.field == "resistance_ohm")
    assert issue.error_code == ErrorCode.INVALID_FIELD
    assert issue.raw_value == value
    assert issue.suggested_fix


def test_actual_writer_defensively_rejects_unrepresentable_numeric(
    tmp_path: Path,
) -> None:
    validated = validate_rows([imported_row()])
    row = validated.rows[0]
    changed_values = row.values.model_copy(update={"resistance_ohm": "9" * 309})
    changed = row.model_copy(update={"values": changed_values})
    destination = tmp_path / "must-not-exist.xlsx"
    with pytest.raises(UnsupportedExcelNumeric):
        write_actual_workbook(destination, [changed])
    assert not destination.exists()


def test_extreme_finite_decimal_is_a_row_issue_and_writer_has_no_side_effect(
    tmp_path: Path,
) -> None:
    huge_decimal = Decimal("1e1000000")
    result = validate_rows(
        [
            imported_row(
                changes={"resistance_ohm": huge_decimal, "tolerance_ohm": "0"}
            )
        ]
    )
    assert result.has_errors
    assert result.source_rows[0].raw.resistance_ohm == huge_decimal
    issue = next(issue for issue in result.issues if issue.field == "resistance_ohm")
    assert issue.error_code == ErrorCode.INVALID_FIELD
    assert issue.raw_value == huge_decimal

    valid_row = validate_rows([imported_row()]).rows[0]
    huge_text = "1" + "0" * 1_000_000
    changed_values = valid_row.values.model_copy(
        update={"resistance_ohm": huge_text}
    )
    changed_row = valid_row.model_copy(update={"values": changed_values})
    destination = tmp_path / "new-parent" / "actual.xlsx"
    with pytest.raises(UnsupportedExcelNumeric):
        write_actual_workbook(destination, [changed_row])
    assert not destination.parent.exists()
    existing = tmp_path / "existing.xlsx"
    existing.write_bytes(b"existing-sentinel")
    with pytest.raises(UnsupportedExcelNumeric):
        write_actual_workbook(existing, [changed_row])
    assert existing.read_bytes() == b"existing-sentinel"


def test_cli_extreme_finite_decimal_retains_source_rows_and_raw_value(
    tmp_path: Path,
) -> None:
    source = REVIEW_FIX_1 / "checks/finite-decimal-context-overflow.xlsx"
    output = tmp_path / "finite-decimal.json"
    actual = tmp_path / "finite-decimal-actual.xlsx"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_excel.py"),
            "--input",
            str(source),
            "--output",
            str(output),
            "--actual-output",
            str(actual),
        ],
        cwd=ROOT,
        check=False,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert process.returncode == 1
    assert payload["status"] == "invalid"
    assert [row["source"]["excel_row"] for row in payload["source_rows"]] == [
        2,
        3,
        4,
    ]
    issue = next(
        item
        for item in payload["issues"]
        if item["excel_row"] == 3 and item["field"] == "resistance_ohm"
    )
    assert issue["error_code"] == "INVALID_FIELD"
    assert issue["raw_value"] == "1" + "0" * 1_000_000
    assert issue["suggested_fix"]
    assert payload["source_rows"][1]["raw"]["resistance_ohm"] == issue["raw_value"]
    assert payload["outputs"] == []
    assert not actual.exists()


@pytest.mark.parametrize(
    "index",
    ["-1", "999999", "-999999", "1.5", "not-an-index", "+1", " 1", ""],
)
def test_invalid_shared_string_references_are_workbook_issues(
    tmp_path: Path, index: str
) -> None:
    source = _shared_string_reference_workbook(tmp_path, "invalid-index", index)
    parsed = parse_workbook(source)
    assert parsed.has_errors
    assert parsed.rows == ()
    assert len(parsed.issues) == 1
    issue = parsed.issues[0]
    assert issue.error_code == ErrorCode.UNSUPPORTED_INPUT
    assert issue.scope.value == "workbook"
    assert not issue.skippable


def test_missing_shared_string_reference_value_is_a_workbook_issue(
    tmp_path: Path,
) -> None:
    source = _shared_string_reference_workbook(tmp_path, "missing-index", None)
    parsed = parse_workbook(source)
    assert parsed.has_errors
    assert parsed.rows == ()
    assert parsed.issues[0].error_code == ErrorCode.UNSUPPORTED_INPUT


@pytest.mark.parametrize("index", ["0", "44", "00044"])
def test_valid_shared_string_reference_boundaries_are_accepted(
    tmp_path: Path, index: str
) -> None:
    source = _shared_string_reference_workbook(tmp_path, "valid-index", index)
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows)
    assert not parsed.has_errors
    assert not validated.has_errors
    assert len(validated.rows) == 3


@pytest.mark.parametrize(
    ("target", "index", "valid"),
    [
        ("worksheets/heaters.xml", "-1", False),
        ("/xl/worksheets/heaters.xml", "-1", False),
        ("worksheets/heaters.xml", "0", True),
        ("/xl/worksheets/heaters.xml", "0", True),
    ],
)
def test_shared_string_validation_follows_renamed_worksheet_relationships(
    tmp_path: Path, target: str, index: str, valid: bool
) -> None:
    def package_edit(package: dict[str, bytes]) -> None:
        _rename_worksheet(package, target)

    source = _shared_string_reference_workbook(
        tmp_path, "renamed-worksheet", index, package_edit
    )
    parsed = parse_workbook(source)
    if valid:
        validated = validate_rows(parsed.rows)
        assert not parsed.has_errors
        assert not validated.has_errors
        assert validated.rows[1].values.standards_reviewer == "阻值偏差(Ω)"
    else:
        assert parsed.has_errors
        assert parsed.rows == ()
        assert parsed.issues[0].error_code == ErrorCode.UNSUPPORTED_INPUT


def test_default_worksheet_content_type_respects_override_precedence(
    tmp_path: Path,
) -> None:
    def package_edit(package: dict[str, bytes]) -> None:
        _use_default_worksheet_content_type(package)
        unused = ElementTree.fromstring(package["xl/worksheets/sheet1.xml"])
        cell = next(
            item
            for item in unused.iter(f"{{{SPREADSHEET_NAMESPACE}}}c")
            if item.attrib.get("r") == "O3"
        )
        cell.find(f"{{{SPREADSHEET_NAMESPACE}}}v").text = "-1"
        package["xl/worksheets/unused.xml"] = ElementTree.tostring(unused)

        content_types = ElementTree.fromstring(package["[Content_Types].xml"])
        ElementTree.SubElement(
            content_types,
            f"{{{CONTENT_TYPES_NAMESPACE}}}Override",
            {
                "PartName": "/xl/worksheets/unused.xml",
                "ContentType": "application/xml",
            },
        )
        package["[Content_Types].xml"] = ElementTree.tostring(content_types)

    source = _shared_string_reference_workbook(
        tmp_path, "default-with-override", "0", package_edit
    )
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows)
    assert not parsed.has_errors
    assert not validated.has_errors
    assert validated.rows[1].values.standards_reviewer == "阻值偏差(Ω)"


@pytest.mark.parametrize(
    ("fixture", "valid"),
    [("default-negative.xlsx", False), ("default-first.xlsx", True)],
)
def test_cli_handles_review_default_worksheet_content_type(
    tmp_path: Path, fixture: str, valid: bool
) -> None:
    process, payload, actual = _run_excel_cli(tmp_path, REVIEW_FIX_2 / fixture)
    if valid:
        assert process.returncode == 0
        assert payload["status"] == "valid"
        assert payload["rows"][1]["standards_reviewer"] == "阻值偏差(Ω)"
        assert actual.exists()
    else:
        assert process.returncode == 1
        assert payload["status"] == "invalid"
        assert payload["record_count"] == 0
        assert payload["source_rows"] == []
        assert payload["outputs"] == []
        assert payload["issues"][0]["scope"] == "workbook"
        assert payload["issues"][0]["error_code"] == "UNSUPPORTED_INPUT"
        assert not actual.exists()


@pytest.mark.parametrize(
    ("fixture", "valid"),
    [("active-workbook-negative.xlsx", False), ("active-workbook-first.xlsx", True)],
)
def test_cli_follows_review_active_workbook_part(
    tmp_path: Path, fixture: str, valid: bool
) -> None:
    process, payload, actual = _run_excel_cli(tmp_path, REVIEW_FIX_3 / fixture)
    if valid:
        assert process.returncode == 0
        assert payload["status"] == "valid"
        assert payload["rows"][1]["standards_reviewer"] == "阻值偏差(Ω)"
        assert actual.exists()
    else:
        assert process.returncode == 1
        assert payload["status"] == "invalid"
        assert payload["record_count"] == 0
        assert payload["source_rows"] == []
        assert payload["outputs"] == []
        assert payload["issues"][0]["scope"] == "workbook"
        assert payload["issues"][0]["error_code"] == "UNSUPPORTED_INPUT"
        assert not payload["issues"][0]["skippable"]
        assert not actual.exists()


@pytest.mark.parametrize(
    "package_edit",
    [_add_ambiguous_workbook_part, _mismatch_root_workbook_relationship],
)
def test_ambiguous_or_inconsistent_workbook_entry_is_rejected(
    tmp_path: Path, package_edit: Callable[[dict[str, bytes]], None]
) -> None:
    source = _shared_string_reference_workbook(
        tmp_path, "invalid-workbook-entry", "0", package_edit
    )
    parsed = parse_workbook(source)
    assert parsed.has_errors
    assert parsed.rows == ()
    assert len(parsed.issues) == 1
    issue = parsed.issues[0]
    assert issue.error_code == ErrorCode.UNSUPPORTED_INPUT
    assert issue.scope.value == "workbook"
    assert not issue.skippable


@pytest.mark.parametrize(
    "source",
    [
        REVIEW_FIX_1 / "checks/bad-string-index.xlsx",
        REVIEW_FIX_1 / "checks/bad-string-index-negative.xlsx",
        REVIEW_FIX_1 / "string-boundary/negative-one.xlsx",
    ],
)
def test_cli_rejects_review_shared_string_inputs_with_complete_json(
    tmp_path: Path, source: Path
) -> None:
    output = tmp_path / f"{source.stem}.json"
    actual = tmp_path / f"{source.stem}-actual.xlsx"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_excel.py"),
            "--input",
            str(source),
            "--output",
            str(output),
            "--actual-output",
            str(actual),
        ],
        cwd=ROOT,
        check=False,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert process.returncode == 1
    assert payload["status"] == "invalid"
    assert payload["record_count"] == 0
    assert payload["source_rows"] == []
    assert payload["outputs"] == []
    assert payload["issues"][0]["scope"] == "workbook"
    assert payload["issues"][0]["error_code"] == "UNSUPPORTED_INPUT"
    assert not actual.exists()


def test_cli_accepts_review_last_shared_string_index(tmp_path: Path) -> None:
    source = REVIEW_FIX_1 / "string-boundary/last-valid.xlsx"
    output = tmp_path / "last-valid.json"
    actual = tmp_path / "last-valid-actual.xlsx"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_excel.py"),
            "--input",
            str(source),
            "--output",
            str(output),
            "--actual-output",
            str(actual),
        ],
        cwd=ROOT,
        check=False,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert process.returncode == 0
    assert payload["status"] == "valid"
    assert payload["rows"][1]["standards_reviewer"] == "CX-29-KR05-XM01"
    assert payload["outputs"] == [
        {"kind": "excel_actual", "path": str(actual)}
    ]
    assert actual.exists()


@pytest.mark.parametrize(
    "source",
    [
        REVIEW_LINUX / "missing-shared-strings.xlsx",
        REVIEW_LINUX / "missing-workbook-rels.xlsx",
        REVIEW_FOCUSED / "corrupt-deflate.xlsx",
    ],
)
def test_damaged_xlsx_is_a_non_skippable_workbook_issue(source: Path) -> None:
    parsed = parse_workbook(source)
    assert parsed.has_errors
    assert parsed.rows == ()
    assert any(
        issue.error_code == ErrorCode.UNSUPPORTED_INPUT
        and issue.scope.value == "workbook"
        and not issue.skippable
        for issue in parsed.issues
    )


@pytest.mark.parametrize(
    "source",
    [
        REVIEW_LINUX / "excel-error-person.xlsx",
        REVIEW_LINUX / "date-person.xlsx",
    ],
)
def test_error_and_date_cells_keep_type_and_are_rejected(source: Path) -> None:
    parsed = parse_workbook(source)
    assert parsed.rows[1].cell_types["standards_reviewer"] in {"d", "e"}
    result = validate_rows(parsed.rows)
    issue = next(
        issue
        for issue in result.issues
        if issue.excel_row == 3 and issue.field == "standards_reviewer"
    )
    assert issue.error_code == ErrorCode.INVALID_FIELD
    assert issue.raw_value is not None
    assert all(row.source.excel_row != 3 for row in result.rows)


@pytest.mark.parametrize("literal", ["#N/A", "2026-11-09T00:00:00"])
def test_error_and_date_looking_text_remains_valid(
    tmp_path: Path, literal: str
) -> None:
    values = dict(VALID_VALUES)
    values["standards_reviewer"] = literal
    source = make_workbook(tmp_path / "literal.xlsx", rows=[values_list(values)])
    workbook = load_workbook(source)
    cell = workbook["Sheet1"]["O2"]
    cell.value = literal
    cell.data_type = "s"
    workbook.save(source)
    workbook.close()

    parsed = parse_workbook(source)
    result = validate_rows(parsed.rows)
    assert parsed.rows[0].cell_types["standards_reviewer"] == "s"
    assert not parsed.has_errors
    assert not result.has_errors
    assert result.rows[0].values.standards_reviewer == literal


def test_direct_datetime_value_is_rejected_without_string_coercion() -> None:
    row = imported_row(changes={"standards_reviewer": datetime(2026, 11, 9)})
    result = validate_rows([row])
    assert result.has_errors
    assert isinstance(result.source_rows[0].raw.standards_reviewer, datetime)


@pytest.mark.parametrize(
    "changes",
    [
        {"max_text_characters": 300},
        {"max_compression_ratio": float("nan")},
        {"max_compression_ratio": float("inf")},
        {"max_file_bytes": float("inf")},
        {"max_business_rows": 0.5},
        {"max_business_rows": True},
    ],
)
def test_invalid_workbook_limit_configuration_is_rejected(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        WorkbookLimits(**changes)


def test_scale_obeys_configured_text_limit_before_parsing() -> None:
    scale = "1:" + "2" * 257
    result = validate_rows([imported_row(changes={"requested_scale": scale})])
    issue = next(issue for issue in result.issues if issue.field == "requested_scale")
    assert "256" in issue.message
    assert issue.raw_value == scale


@pytest.mark.parametrize(
    ("source", "extra"),
    [
        (REVIEW_LINUX / "missing-shared-strings.xlsx", []),
        (REVIEW_LINUX / "missing-workbook-rels.xlsx", []),
        (REVIEW_FOCUSED / "corrupt-deflate.xlsx", []),
        (REVIEW_FOCUSED / "nan-ratio.xlsx", ["--max-compression-ratio", "nan"]),
    ],
)
def test_cli_failures_always_write_complete_json(
    tmp_path: Path, source: Path, extra: list[str]
) -> None:
    output = tmp_path / f"{source.stem}.json"
    actual = tmp_path / f"{source.stem}-actual.xlsx"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_excel.py"),
            "--input",
            str(source),
            "--output",
            str(output),
            "--actual-output",
            str(actual),
            *extra,
        ],
        cwd=ROOT,
        check=False,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result.returncode == 1
    assert payload["status"] == "invalid"
    assert payload["outputs"] == []
    assert payload["issues"]
    assert not actual.exists()
    if extra:
        assert payload["issues"][0]["error_code"] == "INVALID_REQUEST"
        assert payload["source_rows"] == []


def test_cli_rejects_text_limit_above_public_model_limit(tmp_path: Path) -> None:
    output = tmp_path / "invalid-limit.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_excel.py"),
            "--input",
            str(REVIEW_LINUX / "configured-text-300.xlsx"),
            "--output",
            str(output),
            "--max-text-characters",
            "300",
        ],
        cwd=ROOT,
        check=False,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result.returncode == 1
    assert payload["issues"][0]["error_code"] == "INVALID_REQUEST"
    assert payload["outputs"] == []


@pytest.mark.parametrize("code", ["HEATER-COM1", "COM10", "LPT0", "HX.1"])
def test_safe_codes_near_reserved_names_remain_valid(code: str) -> None:
    result = validate_rows([imported_row(changes={"code": code})])
    assert not result.has_errors
