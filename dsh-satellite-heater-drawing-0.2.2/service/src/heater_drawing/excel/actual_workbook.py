"""Write the 17-field actual workbook without formula interpretation."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from openpyxl import Workbook

from heater_drawing.domain.models import Decision, DecisionKind, HeaterRow, Scale
from heater_drawing.excel.headers import FIELD_ORDER, headers_in_order
from heater_drawing.excel.numeric import exact_excel_numeric


NUMERIC_FIELDS = {
    "width_mm",
    "length_mm",
    "resistance_ohm",
    "tolerance_ohm",
}


def _write_text(cell: object, value: str) -> None:
    cell.value = value
    cell.data_type = "s"


def write_actual_workbook(
    path: str | Path,
    rows: Iterable[HeaterRow],
    *,
    final_scales: Mapping[str, Scale] | None = None,
    all_rows: Iterable[HeaterRow] | None = None,
    skipped_row_ids: Iterable[str] = (),
    decisions: Iterable[Decision] = (),
    revision_hash: str | None = None,
) -> Path:
    """Write original text and normalized numeric values to a new workbook."""

    materialized_rows = tuple(rows)
    source_rows = tuple(all_rows) if all_rows is not None else materialized_rows
    scales = dict(final_scales or {})
    skipped = set(skipped_row_ids)
    decision_list = tuple(decisions)
    numeric_values = tuple(
        {
            field: exact_excel_numeric(getattr(row.values, field))
            for field in NUMERIC_FIELDS
        }
        for row in materialized_rows
    )
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    for column, header in enumerate(headers_in_order(), start=1):
        _write_text(sheet.cell(1, column), header)

    for excel_row, (row, row_numeric_values) in enumerate(
        zip(materialized_rows, numeric_values, strict=True), start=2
    ):
        for column, field in enumerate(FIELD_ORDER, start=1):
            cell = sheet.cell(excel_row, column)
            if field in NUMERIC_FIELDS:
                cell.value = row_numeric_values[field]
            elif field == "requested_scale" and row.row_id in scales:
                _write_text(cell, scales[row.row_id].label)
            else:
                raw = getattr(row.raw, field)
                if not isinstance(raw, str):
                    raw = str(raw)
                _write_text(cell, raw)

    if revision_hash is not None:
        changes = workbook.create_sheet("变更记录")
        change_headers = (
            "row_id", "原Excel行", "状态", "原比例", "最终比例", "跳过原因",
            "确认者", "确认时间", "确认回执", "revision_hash",
        )
        for column, header in enumerate(change_headers, start=1):
            _write_text(changes.cell(1, column), header)
        for output_row, row in enumerate(source_rows, start=2):
            matching = [
                decision for decision in decision_list
                if row.row_id in decision.row_ids
            ]
            skip_decision = next(
                (item for item in matching if item.kind == DecisionKind.SKIP), None
            )
            scale_decision = next(
                (item for item in matching if item.kind == DecisionKind.SCALE), None
            )
            decision = skip_decision or scale_decision
            original_scale = row.values.requested_scale
            final_scale = scales[row.row_id].label if row.row_id in scales else original_scale
            values = (
                row.row_id,
                str(row.source.excel_row),
                "skipped" if row.row_id in skipped else "delivered",
                original_scale,
                final_scale,
                skip_decision.reason if skip_decision else "",
                decision.actor_id if decision else "",
                decision.decided_at.isoformat() if decision else "",
                decision.confirmation_receipt_id if decision else "",
                revision_hash,
            )
            for column, value in enumerate(values, start=1):
                _write_text(changes.cell(output_row, column), value)

    temporary = destination.with_name(f".{destination.name}.tmp.xlsx")
    try:
        workbook.save(temporary)
        temporary.replace(destination)
    finally:
        workbook.close()
        if temporary.exists():
            temporary.unlink()
    return destination
