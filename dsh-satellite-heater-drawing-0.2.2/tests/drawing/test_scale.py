from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from heater_drawing.domain.models import Decision, DecisionKind, Scale
from heater_drawing.drawing.dxf_writer import export_planned_dxf
from heater_drawing.drawing.layout import plan_pages

from .conftest import revision_for


def _changed(row, **changes):
    values = row.values.model_copy(update=changes)
    return row.model_copy(update={"values": values})


def test_oversize_proposes_smallest_working_standard_scale(controlled_template, real_rows):
    row = _changed(real_rows[1][2], requested_scale="1:1")
    revision = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: Scale(denominator="1", label="1:1")},
    )
    result = plan_pages(revision, controlled_template)
    assert not result.pages and not result.issues
    assert len(result.proposals) == 1
    assert result.proposals[0].original.label == "1:1"
    assert result.proposals[0].proposed.label == "1:2"


def test_unconfirmed_proposal_cannot_export(tmp_path, controlled_template, real_rows):
    row = _changed(real_rows[1][2], requested_scale="1:1")
    revision = revision_for(controlled_template, [row], scales={row.row_id: Scale(denominator="1", label="1:1")})
    result = plan_pages(revision, controlled_template)
    try:
        export_planned_dxf(
            tmp_path / "forbidden.dxf", result, revision, controlled_template
        )
    except ValueError as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("formal export accepted an unconfirmed proposal")
    assert not (tmp_path / "forbidden.dxf").exists()


def _scale_decision(proposal, row_id, **changes):
    values = {
        "decision_id": UUID("2a5aba91-b6c0-41f2-a465-1ba603e9c7ac"),
        "actor_id": "scale-reviewer",
        "decided_at": datetime(2026, 11, 9, tzinfo=timezone.utc),
        "kind": DecisionKind.SCALE,
        "base_revision_hash": proposal.revision_hash,
        "proposal_ids": [proposal.proposal_id],
        "row_ids": [row_id],
        "reason": "accepted smaller drawing scale",
        "confirmation_receipt_id": "receipt-scale-1",
    }
    values.update(changes)
    return Decision(**values)


def test_pending_proposal_survives_changed_final_scale_and_blocks_export(
    tmp_path, controlled_template, real_rows
):
    row = _changed(real_rows[1][2], requested_scale="1:1")
    initial = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: Scale(denominator="1", label="1:1")},
    )
    proposal = plan_pages(initial, controlled_template).proposals[0]
    changed = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: proposal.proposed},
        proposals=[proposal],
    )
    result = plan_pages(changed, controlled_template)
    assert result.proposals == (proposal,)
    assert result.issues and not result.exportable
    output = tmp_path / "unaccepted.dxf"
    with pytest.raises(ValueError, match="forbidden"):
        export_planned_dxf(output, result, changed, controlled_template)
    assert not output.exists()


def test_valid_scale_decision_binds_proposal_revision_row_scale_and_receipt(
    tmp_path, controlled_template, real_rows
):
    row = _changed(real_rows[1][2], requested_scale="1:1")
    initial = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: Scale(denominator="1", label="1:1")},
    )
    proposal = plan_pages(initial, controlled_template).proposals[0]
    accepted = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: proposal.proposed},
        proposals=[proposal],
        decisions=[_scale_decision(proposal, row.row_id)],
    )
    result = plan_pages(accepted, controlled_template)
    assert result.exportable and not result.proposals and not result.issues
    output = tmp_path / "accepted.dxf"
    export_planned_dxf(output, result, accepted, controlled_template)
    assert output.is_file()


@pytest.mark.parametrize(
    "decision_changes",
    [
        {"base_revision_hash": "b" * 64},
        {"row_ids": ["Sheet1:999"]},
    ],
)
def test_mismatched_scale_decision_is_rejected(
    decision_changes, controlled_template, real_rows
):
    row = _changed(real_rows[1][2], requested_scale="1:1")
    initial = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: Scale(denominator="1", label="1:1")},
    )
    proposal = plan_pages(initial, controlled_template).proposals[0]
    revision = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: proposal.proposed},
        proposals=[proposal],
        decisions=[_scale_decision(proposal, row.row_id, **decision_changes)],
    )
    result = plan_pages(revision, controlled_template)
    assert result.issues and result.proposals == (proposal,)
    assert not result.exportable


def test_fabricated_proposal_base_revision_is_rejected(
    controlled_template, real_rows
):
    row = _changed(real_rows[1][2], requested_scale="1:1")
    initial = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: Scale(denominator="1", label="1:1")},
    )
    proposal = plan_pages(initial, controlled_template).proposals[0].model_copy(
        update={"revision_hash": "b" * 64}
    )
    revision = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: proposal.proposed},
        proposals=[proposal],
        decisions=[_scale_decision(proposal, row.row_id)],
    )
    result = plan_pages(revision, controlled_template)
    assert result.issues and not result.exportable


def test_accepted_proposal_must_equal_final_scale(controlled_template, real_rows):
    row = _changed(real_rows[1][2], requested_scale="1:1")
    initial = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: Scale(denominator="1", label="1:1")},
    )
    proposal = plan_pages(initial, controlled_template).proposals[0]
    revision = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: Scale(denominator="5", label="1:5")},
        proposals=[proposal],
        decisions=[_scale_decision(proposal, row.row_id)],
    )
    result = plan_pages(revision, controlled_template)
    assert result.issues and result.proposals == (proposal,)
    assert not result.exportable


def test_scale_decision_requires_confirmation_receipt(controlled_template, real_rows):
    row = _changed(real_rows[1][2], requested_scale="1:1")
    initial = revision_for(
        controlled_template,
        [row],
        scales={row.row_id: Scale(denominator="1", label="1:1")},
    )
    proposal = plan_pages(initial, controlled_template).proposals[0]
    with pytest.raises(ValidationError):
        _scale_decision(proposal, row.row_id, confirmation_receipt_id="")


def test_no_standard_scale_solution_is_an_explicit_row_error(controlled_template, real_rows):
    row = _changed(real_rows[1][0], width_mm="100000", length_mm="100000", requested_scale="1:1")
    revision = revision_for(controlled_template, [row])
    result = plan_pages(revision, controlled_template)
    assert not result.pages and not result.proposals
    assert len(result.issues) == 1
    assert "无可行排版" in result.issues[0].message


def test_long_title_text_is_not_solved_by_scaling(controlled_template, real_rows):
    row = _changed(real_rows[1][0], organization="超" * 120)
    revision = revision_for(controlled_template, [row])
    result = plan_pages(revision, controlled_template)
    assert result.issues and not result.proposals
    assert "text" in result.issues[0].message or "文字" in result.issues[0].message


def test_missing_glyph_is_rejected_before_export(controlled_template, real_rows):
    row = _changed(real_rows[1][0], code="MISSING-GLYPH-\U0001F642")
    revision = revision_for(controlled_template, [row])
    result = plan_pages(revision, controlled_template)
    assert result.issues and not result.proposals and not result.pages
    assert "glyph" in result.issues[0].message


def test_small_sheet_lead_dimension_clearance_boundary(controlled_template, real_rows):
    one = _changed(real_rows[1][0], width_mm="1", length_mm="1")
    rejected = plan_pages(revision_for(controlled_template, [one]), controlled_template)
    assert rejected.issues and "0.25" in rejected.issues[0].message
    assert not rejected.pages and not rejected.proposals

    two = _changed(real_rows[1][0], width_mm="2", length_mm="2")
    accepted = plan_pages(revision_for(controlled_template, [two]), controlled_template)
    assert accepted.exportable
