from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile
from io import BytesIO

from openpyxl import load_workbook

from heater_drawing.domain.models import ErrorCode
from heater_drawing.excel import WorkbookLimits, parse_workbook
from tests.excel.helpers import make_workbook, values_list


def test_rejects_wrong_extension_and_disguised_or_corrupt_xlsx(tmp_path: Path) -> None:
    fake = tmp_path / "fake.xlsx"
    fake.write_text("not a zip", encoding="utf-8")
    wrong = tmp_path / "book.xls"
    wrong.write_bytes(fake.read_bytes())
    for source in (fake, wrong):
        parsed = parse_workbook(source)
        assert parsed.has_errors
        assert parsed.issues[0].error_code == ErrorCode.UNSUPPORTED_INPUT


def test_zip_entry_and_uncompressed_limits_are_enforced(tmp_path: Path) -> None:
    source = make_workbook(tmp_path / "limits.xlsx")
    assert parse_workbook(source, {"max_zip_entries": 1}).issues[0].error_code == ErrorCode.PAYLOAD_TOO_LARGE
    assert parse_workbook(source, {"max_uncompressed_bytes": 100}).issues[0].error_code == ErrorCode.PAYLOAD_TOO_LARGE


def test_compression_bomb_ratio_is_rejected_before_openpyxl(tmp_path: Path) -> None:
    source = tmp_path / "bomb.xlsx"
    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "A" * 100_000)
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    parsed = parse_workbook(source, {"max_compression_ratio": 10})
    assert parsed.has_errors
    assert parsed.issues[0].error_code == ErrorCode.PAYLOAD_TOO_LARGE


def test_external_relationship_and_macro_payload_are_rejected(tmp_path: Path) -> None:
    for mode in ("external", "macro"):
        original = make_workbook(tmp_path / f"{mode}-source.xlsx")
        output = tmp_path / f"{mode}.xlsx"
        source_buffer = BytesIO(original.read_bytes())
        target_buffer = BytesIO()
        with ZipFile(source_buffer) as source, ZipFile(
            target_buffer, "w", compression=ZIP_DEFLATED
        ) as target:
            for info in source.infolist():
                target.writestr(info, source.read(info))
            if mode == "external":
                target.writestr(
                    "xl/worksheets/_rels/sheet1.xml.rels",
                    """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.invalid" TargetMode="External"/>
</Relationships>""",
                )
            else:
                target.writestr("xl/vbaProject.bin", b"not-a-real-macro")
        output.write_bytes(target_buffer.getvalue())
        parsed = parse_workbook(output)
        assert parsed.has_errors
        assert parsed.issues[0].error_code == ErrorCode.UNSUPPORTED_INPUT


def test_business_row_limit_retains_all_rows_in_report(tmp_path: Path) -> None:
    source = make_workbook(
        tmp_path / "rows.xlsx",
        rows=[values_list(), values_list(), values_list()],
    )
    workbook = load_workbook(source)
    sheet = workbook["Sheet1"]
    sheet["B3"] = "HX-02"
    sheet["B4"] = "HX-03"
    workbook.save(source)
    workbook.close()
    parsed = parse_workbook(source, {"max_business_rows": 2})
    assert len(parsed.rows) == 3
    assert any(issue.error_code == ErrorCode.PAYLOAD_TOO_LARGE for issue in parsed.issues)


def test_column_limit_ignores_formatted_blank_but_rejects_real_value(tmp_path: Path) -> None:
    source = make_workbook(tmp_path / "columns.xlsx")
    workbook = load_workbook(source)
    sheet = workbook["Sheet1"]
    sheet["Z20"].number_format = "0.00"
    workbook.save(source)
    workbook.close()
    assert not parse_workbook(source, {"max_columns": 17}).has_errors

    workbook = load_workbook(source)
    workbook["Sheet1"]["Z20"] = "real value"
    workbook.save(source)
    workbook.close()
    parsed = parse_workbook(source, {"max_columns": 17})
    assert parsed.issues[0].error_code == ErrorCode.PAYLOAD_TOO_LARGE


def test_configured_file_limit_is_enforced(tmp_path: Path) -> None:
    source = make_workbook(tmp_path / "file-size.xlsx")
    parsed = parse_workbook(
        source, WorkbookLimits(max_file_bytes=100)
    )
    assert parsed.issues[0].error_code == ErrorCode.PAYLOAD_TOO_LARGE


def test_invalid_cli_returns_one_and_keeps_every_source_row(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "fixtures/invalid/invalid-values.xlsx"
    if not source.exists():
        subprocess.run(
            [sys.executable, str(root / "scripts/build_b03_fixtures.py")],
            cwd=root,
            check=True,
        )
    output = tmp_path / "invalid.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/check_excel.py"),
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        cwd=root,
        check=False,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result.returncode == 1
    assert payload["status"] == "invalid"
    assert [row["source"]["excel_row"] for row in payload["source_rows"]] == [2, 3]
    assert payload["source_rows"][1]["values"] is None
    assert payload["source_rows"][1]["issue_ids"]
    assert payload["outputs"] == []
