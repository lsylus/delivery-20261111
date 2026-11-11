from __future__ import annotations

import hashlib
import json

from openpyxl import load_workbook

from heater_drawing.delivery import validate_delivery

from .conftest import ROOT


def test_complete_case_has_exact_order_hashes_and_traceability(delivery_case) -> None:
    root, revision = delivery_case
    result = validate_delivery(
        root, revision, template_dir=ROOT / "templates/heater-a4-v1"
    )
    assert result["status"] == "passed"
    assert result["expected_row_ids"] == ["Sheet1:2", "Sheet1:3", "Sheet1:4"]
    assert result["page_count"] == 3
    assert hashlib.sha256((root / "original.xlsx").read_bytes()).hexdigest() == revision.source_sha256
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["page_mapping"] == [
        {"page_index": 1, "row_id": "Sheet1:2", "code": "CX-29-KR05-XM01", "relative_path": "pdf/CX-29-KR05-XM01.pdf"},
        {"page_index": 2, "row_id": "Sheet1:3", "code": "CX-26-KR05-DLL-01", "relative_path": "pdf/CX-26-KR05-DLL-01.pdf"},
        {"page_index": 3, "row_id": "Sheet1:4", "code": "KX-11-WR-100-300-M1", "relative_path": "pdf/KX-11-WR-100-300-M1.pdf"},
    ]
    assert manifest["formats"]["dwg"] == {"status": "disabled_not_provided", "artifacts": []}
    assert all(item["relative_path"] != "manifest.json" for item in manifest["files"])
    workbook = load_workbook(root / "actual.xlsx", data_only=False)
    try:
        assert workbook["Sheet1"]["O3"].value == "郑玲"
        assert workbook["Sheet1"]["H3"].value == "12（备份2）"
        assert workbook["Sheet1"]["H4"].value == "76片（备份13片）"
        assert workbook["变更记录"].max_row == 4
    finally:
        workbook.close()
