#!/usr/bin/env python3
"""Rebuild deterministic B05-only frozen revision fixtures."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

from heater_drawing.domain.errors import make_issue
from heater_drawing.domain.models import (
    Decision, DecisionKind, ErrorCode, IssueScope, Revision, Scale, Severity,
)
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.template import load_template
from heater_drawing.excel import parse_workbook, validate_rows


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = UUID("f4ffb417-4b69-4137-8053-2fcff4bde248")
FIXTURE_TIME = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)


def _write(name: str, revision: Revision) -> None:
    path = ROOT / "fixtures/delivery" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(revision.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _base_revision() -> tuple[Revision, dict]:
    source = ROOT / "fixtures/case/加热器图纸.xlsx"
    template = load_template(ROOT / "templates/heater-a4-v1")
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows, template)
    if parsed.has_errors or validated.has_errors:
        raise ValueError("real case must remain valid")
    scales = {
        row.row_id: Scale(
            denominator=row.values.requested_scale.split(":", 1)[1],
            label=row.values.requested_scale,
        )
        for row in validated.rows
    }
    revision = Revision.create(
        revision_id=uuid5(NAMESPACE, "case"),
        parent_revision_id=None,
        source_sha256=parsed.source_sha256,
        template_version=template["manifest"]["version"],
        template_hash=template["template_sha256"],
        font_manifest_hash=template["fonts_sha256"],
        output_profile="dxf_pdf_v1",
        rows=list(validated.rows),
        final_scales=scales,
        issues=[],
        proposals=[],
        decisions=[],
        skipped_row_ids=[],
        expected_row_ids=[row.row_id for row in validated.rows],
    )
    return revision, template


def main() -> int:
    base, template = _base_revision()
    _write("case-revision.json", base)

    skipped_id = base.rows[1].row_id
    skipped_row = base.rows[1]
    skip_issue = make_issue(
        error_code=ErrorCode.INVALID_FIELD,
        severity=Severity.ERROR,
        message="B05 fixture row is intentionally failed and may only be delivered as an explicit skip",
        suggested_fix="Use the fixture-only skip decision; production requires a real Host receipt",
        scope=IssueScope.ROW,
        row_id=skipped_row.row_id,
        sheet=skipped_row.source.sheet,
        excel_row=skipped_row.source.excel_row,
        code=skipped_row.values.code,
        field="quantity_text",
        raw_value=skipped_row.values.quantity_text,
        skippable=True,
    )
    skip = Decision(
        decision_id=uuid5(NAMESPACE, "skip-excel-row-3"),
        actor_id="b05-test-fixture-actor",
        decided_at=FIXTURE_TIME,
        kind=DecisionKind.SKIP,
        base_revision_hash=base.revision_hash,
        issue_ids=[skip_issue.issue_id],
        proposal_ids=[],
        row_ids=[skipped_id],
        reason="B05 test fixture explicitly skips Excel row 3; not production authorization",
        confirmation_receipt_id="fixture-only-skip-receipt",
    )
    skip_revision = Revision.create(
        revision_id=uuid5(NAMESPACE, "case-skip-excel-row-3"),
        parent_revision_id=base.revision_id,
        source_sha256=base.source_sha256,
        template_version=base.template_version,
        template_hash=base.template_hash,
        font_manifest_hash=base.font_manifest_hash,
        output_profile=base.output_profile,
        rows=base.rows,
        final_scales=base.final_scales,
        issues=[skip_issue],
        proposals=[],
        decisions=[skip],
        skipped_row_ids=[skipped_id],
        expected_row_ids=[base.rows[0].row_id, base.rows[2].row_id],
    )
    _write("case-revision-skip-excel-row-3.json", skip_revision)

    scale_row_id = base.rows[2].row_id
    changed_row = base.rows[2].model_copy(
        update={
            "raw": base.rows[2].raw.model_copy(update={"requested_scale": "1:1"}),
            "values": base.rows[2].values.model_copy(update={"requested_scale": "1:1"}),
        }
    )
    scale_rows = [*base.rows[:2], changed_row]
    original = Revision.create(
        revision_id=uuid5(NAMESPACE, "scale-original"),
        parent_revision_id=None,
        source_sha256="c" * 64,
        template_version=base.template_version,
        template_hash=base.template_hash,
        font_manifest_hash=base.font_manifest_hash,
        output_profile=base.output_profile,
        rows=scale_rows,
        final_scales={
            **{key: value for key, value in base.final_scales.items() if key != scale_row_id},
            scale_row_id: Scale(denominator="1", label="1:1"),
        },
        issues=[], proposals=[], decisions=[], skipped_row_ids=[],
        expected_row_ids=[row.row_id for row in scale_rows],
    )
    proposal_plan = plan_pages(original, template)
    proposal = next(item for item in proposal_plan.proposals if item.row_id == scale_row_id)
    decision = Decision(
        decision_id=uuid5(NAMESPACE, "accept-scale"),
        actor_id="b05-test-fixture-actor",
        decided_at=FIXTURE_TIME,
        kind=DecisionKind.SCALE,
        base_revision_hash=original.revision_hash,
        issue_ids=[],
        proposal_ids=[proposal.proposal_id],
        row_ids=[scale_row_id],
        reason="B05 test fixture accepts generated 1:2 proposal; not production authorization",
        confirmation_receipt_id="fixture-only-scale-receipt",
    )
    accepted = Revision.create(
        revision_id=uuid5(NAMESPACE, "scale-accepted"),
        parent_revision_id=original.revision_id,
        source_sha256=original.source_sha256,
        template_version=original.template_version,
        template_hash=original.template_hash,
        font_manifest_hash=original.font_manifest_hash,
        output_profile=original.output_profile,
        rows=scale_rows,
        final_scales={**original.final_scales, scale_row_id: proposal.proposed},
        issues=[], proposals=[proposal], decisions=[decision], skipped_row_ids=[],
        expected_row_ids=original.expected_row_ids,
    )
    if not plan_pages(accepted, template).exportable:
        raise ValueError("accepted scale fixture must be exportable")
    _write("scale-confirmed-revision.json", accepted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
