from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile

import pytest
from openpyxl import load_workbook

from heater_drawing.delivery import DeliveryError
from heater_drawing.delivery.validation import _validate_workbooks, row_report_contract
from heater_drawing.delivery.workbooks import build_workbooks
from heater_drawing.domain.models import Revision
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.template import load_template

from .conftest import ROOT


SHEET_XML_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def test_explicit_skip_keeps_original_and_delivers_only_expected_rows(skipped_delivery_case) -> None:
    root, revision = skipped_delivery_case
    assert revision.skipped_row_ids == ["Sheet1:3"]
    assert sorted(path.name for path in (root / "pdf").iterdir()) == [
        "CX-29-KR05-XM01.pdf", "KX-11-WR-100-300-M1.pdf"
    ]
    workbook = load_workbook(root / "actual.xlsx", data_only=False)
    original = load_workbook(root / "original.xlsx", data_only=False)
    try:
        assert workbook["Sheet1"].max_row == 3
        assert [workbook["Sheet1"].cell(row, 2).value for row in (2, 3)] == [
            "CX-29-KR05-XM01", "KX-11-WR-100-300-M1"
        ]
        changes = list(workbook["变更记录"].iter_rows(min_row=2, values_only=True))
        assert [item[0] for item in changes] == ["Sheet1:2", "Sheet1:3", "Sheet1:4"]
        assert changes[1][2] == "skipped"
        assert changes[1][5] == "B05 test fixture explicitly skips Excel row 3; not production authorization"
        assert original["Sheet1"].max_row >= 4
    finally:
        workbook.close()
        original.close()


def test_scale_confirmation_fixture_is_exportable_and_retains_receipt() -> None:
    revision = Revision.model_validate_json(
        (ROOT / "fixtures/delivery/scale-confirmed-revision.json").read_text(encoding="utf-8")
    )
    plan = plan_pages(revision, load_template(ROOT / "templates/heater-a4-v1"))
    assert plan.exportable
    assert revision.rows[2].values.requested_scale == "1:1"
    assert revision.final_scales["Sheet1:4"].label == "1:2"
    assert revision.decisions[0].confirmation_receipt_id == "fixture-only-scale-receipt"


def test_row_report_retains_unlocated_global_warning() -> None:
    value = json.loads(
        (ROOT / "fixtures/delivery/case-revision.json").read_text(encoding="utf-8")
    )
    issue = json.loads(
        (
            ROOT / "fixtures/delivery/case-revision-skip-excel-row-3.json"
        ).read_text(encoding="utf-8")
    )["issues"][0]
    issue.update(
        row_id=None,
        sheet=None,
        excel_row=None,
        scope="system",
        severity="warning",
        skippable=False,
    )
    value.pop("revision_hash")
    value["issues"] = [issue]
    revision = Revision.create(**value)

    report = row_report_contract(revision)

    assert report["global_issues"] == [revision.issues[0].model_dump(mode="json")]
    assert all(row["issues"] == [] for row in report["rows"])


def _literal_formula_reason_workbooks(tmp_path):
    value = json.loads(
        (
            ROOT / "fixtures/delivery/case-revision-skip-excel-row-3.json"
        ).read_text(encoding="utf-8")
    )
    value.pop("revision_hash")
    value["decisions"][0]["reason"] = "=1+1"
    revision = Revision.create(**value)
    build_workbooks(
        revision,
        ROOT / "fixtures/case/加热器图纸.xlsx",
        tmp_path,
    )
    return revision


def _add_formula_outside_declared_dimension(
    path, *, coordinate: str, dimension: str
) -> None:
    member = "xl/worksheets/sheet2.xml"
    with zipfile.ZipFile(path) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]

    rewritten = []
    namespace = {"s": SHEET_XML_NAMESPACE}
    qualified = f"{{{SHEET_XML_NAMESPACE}}}"
    for info, data in entries:
        if info.filename == member:
            document = ET.fromstring(data)
            document.find("s:dimension", namespace).set("ref", dimension)
            row_number = "".join(character for character in coordinate if character.isdigit())
            sheet_data = document.find("s:sheetData", namespace)
            row = next(
                (item for item in sheet_data if item.get("r") == row_number),
                None,
            )
            if row is None:
                row = ET.SubElement(sheet_data, f"{qualified}row", {"r": row_number})
            cell = ET.SubElement(row, f"{qualified}c", {"r": coordinate})
            ET.SubElement(cell, f"{qualified}f").text = "1+1"
            ET.SubElement(cell, f"{qualified}v").text = "2"
            data = ET.tostring(document, encoding="utf-8", xml_declaration=True)
        rewritten.append((info, data))

    with zipfile.ZipFile(path, "w") as archive:
        for info, data in rewritten:
            archive.writestr(info, data)


def test_literal_formula_skip_reason_is_text_and_valid(tmp_path) -> None:
    revision = _literal_formula_reason_workbooks(tmp_path)
    workbook = load_workbook(tmp_path / "actual.xlsx", data_only=False)
    try:
        cell = workbook["变更记录"]["F3"]
        assert cell.value == "=1+1"
        assert cell.data_type == "s"
    finally:
        workbook.close()

    _validate_workbooks(tmp_path, revision)


@pytest.mark.parametrize(
    ("sheet_name", "coordinate"),
    [("Sheet1", "A2"), ("变更记录", "F3")],
)
def test_formula_cell_in_any_controlled_sheet_is_rejected(
    tmp_path, sheet_name, coordinate
) -> None:
    revision = _literal_formula_reason_workbooks(tmp_path)
    workbook = load_workbook(tmp_path / "actual.xlsx", data_only=False)
    cell = workbook[sheet_name][coordinate]
    cell.data_type = "f"
    workbook.save(tmp_path / "actual.xlsx")
    workbook.close()

    with pytest.raises(
        DeliveryError,
        match=rf"INVALID_WORKBOOK.*{sheet_name}!{coordinate}",
    ):
        _validate_workbooks(tmp_path, revision)


@pytest.mark.parametrize(
    ("coordinate", "declared_dimension"),
    [("K3", "A1:J4"), ("F5", "A1:J4")],
)
def test_formula_outside_declared_dimension_is_rejected(
    tmp_path, coordinate, declared_dimension
) -> None:
    revision = _literal_formula_reason_workbooks(tmp_path)
    path = tmp_path / "actual.xlsx"
    _add_formula_outside_declared_dimension(
        path,
        coordinate=coordinate,
        dimension=declared_dimension,
    )

    workbook = load_workbook(path, data_only=False, read_only=False)
    try:
        cell = workbook["变更记录"][coordinate]
        assert cell.value == "=1+1"
        assert cell.data_type == "f"
    finally:
        workbook.close()

    with pytest.raises(
        DeliveryError,
        match=rf"INVALID_WORKBOOK.*变更记录!{coordinate}",
    ):
        _validate_workbooks(tmp_path, revision)
