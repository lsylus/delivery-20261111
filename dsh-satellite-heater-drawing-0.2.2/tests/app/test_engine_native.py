"""Real CAD planning and explicit decisions over modified engineer workbooks."""
import os
from pathlib import Path

import pytest
from openpyxl import load_workbook

from heater_drawing.app.engine import analyze, decide
from heater_drawing.drawing.opencadstudio import DEFAULT_EXECUTABLE

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not Path(os.environ.get("HEATER_OPENCADSTUDIO", DEFAULT_EXECUTABLE)).is_file(), reason="native CAD required")


def test_skip_then_scale_requires_exact_confirmation_and_preserves_source(tmp_path):
    source = tmp_path / "decisions.xlsx"
    workbook = load_workbook(ROOT / "fixtures/case/加热器图纸.xlsx")
    sheet = workbook.active
    sheet["C2"], sheet["D2"] = 100, 300
    sheet["H3"] = "12片（备份" + "1" * 140 + "片）"
    workbook.save(source)
    workbook.close()
    original = source.read_bytes()
    template = ROOT / "templates/heater-a4-v1"
    current = analyze(source, template)
    assert not current["exportable"] and not current.get("requires_reupload")
    assert current["proposals"] and current["issues"]
    skippable = [i for i in current["issues"] if i["skippable"] and i["excel_row"] == 3]
    assert skippable
    selection = {"kind": "skip", "row_ids": sorted({i["row_id"] for i in skippable}),
                 "issue_ids": [i["issue_id"] for i in skippable], "proposal_ids": [], "reason": "明确排除超长数量行"}
    with pytest.raises(ValueError):
        decide(current, {**selection, "row_ids": ["unrelated-row"]}, "owner", "receipt", template)
    current = decide(current, selection, "owner", "skip-receipt", template)
    assert current["expected_pages"] == 2 and len(current["skipped_rows"]) == 1
    assert not current["exportable"] and current["proposals"]
    proposals = current["proposals"]
    selection = {"kind": "scale", "row_ids": sorted({p["row_id"] for p in proposals}),
                 "proposal_ids": [p["proposal_id"] for p in proposals], "issue_ids": [], "reason": "接受逐项比例建议"}
    with pytest.raises(ValueError):
        decide(current, {**selection, "proposal_ids": ["stale-proposal"]}, "owner", "receipt", template)
    updated = decide(current, selection, "owner", "scale-receipt", template)
    assert updated["exportable"] and not updated["proposals"]
    assert updated["expected_pages"] == 2
    assert updated["revision"]["revision_hash"] != current["revision"]["revision_hash"]
    assert source.read_bytes() == original


def test_cannot_skip_the_only_remaining_row(tmp_path):
    source = tmp_path / "all-skip.xlsx"
    workbook = load_workbook(ROOT / "fixtures/case/加热器图纸.xlsx")
    sheet = workbook.active
    sheet.delete_rows(3, sheet.max_row)
    sheet["H2"] = "12片（备份" + "1" * 140 + "片）"
    workbook.save(source)
    workbook.close()
    template = ROOT / "templates/heater-a4-v1"
    current = analyze(source, template)
    issues = [i for i in current["issues"] if i["skippable"]]
    assert issues
    with pytest.raises(ValueError, match="不能跳过全部行"):
        decide(current, {"kind": "skip", "row_ids": sorted({i["row_id"] for i in issues}),
                         "issue_ids": [i["issue_id"] for i in issues], "proposal_ids": [],
                         "reason": "测试全量跳过被拒绝"}, "owner", "receipt", template)
