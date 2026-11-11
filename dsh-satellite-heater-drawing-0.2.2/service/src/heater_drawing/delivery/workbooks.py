"""Delivery workbook construction and traceability helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from heater_drawing.domain.models import Revision
from heater_drawing.excel.actual_workbook import write_actual_workbook


def build_workbooks(revision: Revision, original: Path, output: Path) -> tuple[Path, Path]:
    original_target = output / "original.xlsx"
    actual_target = output / "actual.xlsx"
    shutil.copyfile(original, original_target)
    expected = set(revision.expected_row_ids)
    delivered_rows = [row for row in revision.rows if row.row_id in expected]
    write_actual_workbook(
        actual_target,
        delivered_rows,
        final_scales=revision.final_scales,
        all_rows=revision.rows,
        skipped_row_ids=revision.skipped_row_ids,
        decisions=revision.decisions,
        revision_hash=revision.revision_hash,
    )
    return original_target, actual_target
