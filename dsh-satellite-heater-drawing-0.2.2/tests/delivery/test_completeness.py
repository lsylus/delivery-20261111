from __future__ import annotations

import json
import shutil

import pytest
from openpyxl import load_workbook
from pypdf import PdfWriter

from heater_drawing.delivery import DeliveryError, validate_delivery
from heater_drawing.delivery.pdf_merge import merge_single_page_pdfs

from .conftest import ROOT, rebind_candidate


def _validate(root, revision) -> None:
    validate_delivery(root, revision, template_dir=ROOT / "templates/heater-a4-v1")


def test_missing_page_is_rejected(copied_case) -> None:
    root, revision = copied_case
    (root / "pdf/CX-26-KR05-DLL-01.pdf").unlink()
    with pytest.raises(DeliveryError, match="MISSING_ARTIFACT"):
        _validate(root, revision)


def test_duplicate_manifest_page_is_rejected(copied_case) -> None:
    root, revision = copied_case
    path = root / "manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["files"].append(dict(value["files"][1]))
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="NAME_COLLISION"):
        _validate(root, revision)


def test_wrong_merged_order_is_rejected_by_rendered_pages(copied_case) -> None:
    root, revision = copied_case
    singles = [root / f"pdf/{code}.pdf" for code in (
        "CX-29-KR05-XM01", "CX-26-KR05-DLL-01", "KX-11-WR-100-300-M1"
    )]
    merge_single_page_pdfs(list(reversed(singles)), root / "加热器图纸.pdf")
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="PAGE_ORDER_MISMATCH"):
        _validate(root, revision)


def test_extra_residual_file_is_rejected(copied_case) -> None:
    root, revision = copied_case
    (root / "pdf/stale.pdf").write_bytes((root / "pdf/CX-29-KR05-XM01.pdf").read_bytes())
    with pytest.raises(DeliveryError, match="ARTIFACT_SET_MISMATCH"):
        _validate(root, revision)


def test_hash_drift_is_rejected(copied_case) -> None:
    root, revision = copied_case
    with (root / "row-report.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(DeliveryError, match="HASH_MISMATCH"):
        _validate(root, revision)


def test_duplicate_single_content_is_rejected_against_formal_dxf(copied_case) -> None:
    root, revision = copied_case
    first = root / "pdf/CX-29-KR05-XM01.pdf"
    second = root / "pdf/CX-26-KR05-DLL-01.pdf"
    shutil.copyfile(first, second)
    merge_single_page_pdfs(
        [
            root / "pdf/CX-29-KR05-XM01.pdf",
            root / "pdf/CX-26-KR05-DLL-01.pdf",
            root / "pdf/KX-11-WR-100-300-M1.pdf",
        ],
        root / "加热器图纸.pdf",
    )
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="PAGE_CONTENT_MISMATCH"):
        _validate(root, revision)


def test_blank_singles_and_consistent_merge_are_rejected(copied_case) -> None:
    root, revision = copied_case
    singles = [
        root / f"pdf/{code}.pdf"
        for code in (
            "CX-29-KR05-XM01",
            "CX-26-KR05-DLL-01",
            "KX-11-WR-100-300-M1",
        )
    ]
    for single in singles:
        writer = PdfWriter()
        writer.add_blank_page(width=210 * 72 / 25.4, height=297 * 72 / 25.4)
        with single.open("wb") as stream:
            writer.write(stream)
    merge_single_page_pdfs(singles, root / "加热器图纸.pdf")
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="PAGE_CONTENT_MISMATCH"):
        _validate(root, revision)


def test_lost_skip_trace_is_rejected_after_rebinding(copied_skipped_case) -> None:
    root, revision = copied_skipped_case
    workbook = load_workbook(root / "actual.xlsx")
    for cells in workbook["变更记录"].iter_rows(min_row=2):
        for index in (1, 5, 6, 7, 8):
            cells[index].value = "fabricated"
    workbook.save(root / "actual.xlsx")
    workbook.close()
    report_path = root / "row-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["expected_row_ids"] = ["Sheet1:999"]
    report["skipped_row_ids"] = []
    for row in report["rows"]:
        row["skip"] = None
        row["issues"] = []
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="INVALID_WORKBOOK"):
        _validate(root, revision)


def test_inconsistent_manifest_run_and_artifact_bindings_are_rejected(
    copied_case,
) -> None:
    root, revision = copied_case
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["page_mapping"] = []
    manifest["run_id"] = "3d01d30d-a772-4ee4-a8fb-f0f6f03be55a"
    manifest["source_sha256"] = "0" * 64
    for item in manifest["files"]:
        item["revision_hash"] = "0" * 64
        item["run_id"] = "d1831065-617e-42c1-a309-7876d236036e"
        if item["kind"] != "pdf_single":
            item["row_ids"] = ["Sheet1:999"]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    run_path = root / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["expected_row_ids"] = ["Sheet1:999"]
    run_path.write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="INVALID_MANIFEST"):
        _validate(root, revision)
