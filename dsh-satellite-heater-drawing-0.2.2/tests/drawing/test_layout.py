from __future__ import annotations

from heater_drawing.domain.errors import make_issue
from heater_drawing.domain.models import ErrorCode, IssueScope, Severity
from heater_drawing.drawing.layout import plan_pages

from .conftest import revision_for


def test_real_rows_keep_input_order_and_independent_layouts(real_plan):
    assert [page.row_id for page in real_plan.pages] == ["Sheet1:2", "Sheet1:3", "Sheet1:4"]
    assert [page.scale.label for page in real_plan.pages] == ["1:1", "1:1", "1:2"]
    assert len({page.placement.layout_name for page in real_plan.pages}) == 3
    assert [page.placement.model_origin_mm.x for page in real_plan.pages] == ["0", "220", "450"]


def test_planning_is_semantically_deterministic(real_plan, real_revision, controlled_template):
    repeated = plan_pages(real_revision, controlled_template)
    assert repeated == real_plan


def test_any_import_or_validation_error_blocks_the_whole_batch(controlled_template, real_rows):
    row = real_rows[1][0]
    issue = make_issue(
        error_code=ErrorCode.INVALID_FIELD,
        severity=Severity.ERROR,
        message="parser issue retained",
        suggested_fix="repair workbook",
        scope=IssueScope.ROW,
        row_id=row.row_id,
        sheet=row.source.sheet,
        excel_row=row.source.excel_row,
        code=row.values.code,
        field="code",
        raw_value=row.values.code,
        skippable=True,
    )
    revision = revision_for(controlled_template, [row], issues=[issue])
    result = plan_pages(revision, controlled_template)
    assert not result.pages and result.issues == (issue,) and not result.proposals


def test_model_tiles_have_ten_mm_clearance_on_both_adjacent_paper_scales(real_plan):
    pages = real_plan.pages
    for previous, current in zip(pages, pages[1:]):
        gap = float(current.placement.tile_bounds_mm.left) - float(previous.placement.tile_bounds_mm.right)
        assert gap / float(previous.scale.denominator) >= 10
        assert gap / float(current.scale.denominator) >= 10
