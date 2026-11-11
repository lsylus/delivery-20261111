"""Deterministic B04 page planning over immutable revisions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from heater_drawing.domain.errors import make_issue
from heater_drawing.domain.models import (
    Bounds,
    CheckResult,
    DrawingChecks,
    DrawingPage,
    DecisionKind,
    ErrorCode,
    HeaterRow,
    Issue,
    IssueScope,
    Placement,
    Revision,
    Scale,
    ScaleProposal,
    Severity,
    compute_revision_hash,
    validate_revision_hash,
)

from .collision import is_scale_sensitive, preflight_page
from .geometry import build_geometry, decimal_text, point
from .scale import make_scale, recommendation_denominators
from .template import load_template
from .profile import output_template


PROPOSAL_NAMESPACE = UUID("223ca610-8bbd-48f3-a149-7fd9eea54e4b")


@dataclass(frozen=True, slots=True)
class PagePlan:
    revision_hash: str
    template_hash: str
    expected_row_ids: tuple[str, ...]
    pages: tuple[DrawingPage, ...]
    issues: tuple[Issue, ...]
    proposals: tuple[ScaleProposal, ...]
    diagnostics: tuple[dict[str, Any], ...] = ()

    @property
    def exportable(self) -> bool:
        return (
            bool(self.pages)
            and tuple(page.row_id for page in self.pages) == self.expected_row_ids
            and all(page.revision_hash == self.revision_hash for page in self.pages)
            and all(page.template_hash == self.template_hash for page in self.pages)
            and not any(issue.severity == Severity.ERROR for issue in self.issues)
            and not self.proposals
        )


def _row_issue(row: HeaterRow, message: str, field: str = "requested_scale") -> Issue:
    return make_issue(
        error_code=ErrorCode.INVALID_FIELD,
        severity=Severity.ERROR,
        message=message,
        suggested_fix="修正对应字段，或明确接受系统提出的比例后创建新修订",
        scope=IssueScope.ROW,
        row_id=row.row_id,
        sheet=row.source.sheet,
        excel_row=row.source.excel_row,
        code=row.values.code,
        field=field,
        raw_value=getattr(row.values, field, None),
        skippable=True,
    )


def _page(row: HeaterRow, revision: Revision, scale: Scale, template: dict, index: int) -> DrawingPage:
    denominator = Decimal(scale.denominator)
    paper = template["layout"]["paper_mm"]
    geometry = build_geometry(row, denominator, template["layout"])
    return DrawingPage(
        row_id=row.row_id,
        code=row.values.code,
        revision_hash=revision.revision_hash,
        template_hash=revision.template_hash,
        scale=scale,
        geometry_mm=geometry,
        fields=row.values,
        fixed_text_version=template["layout"]["fixed_text_version"],
        placement=Placement(
            model_origin_mm=point(Decimal("0"), Decimal("0")),
            tile_bounds_mm=Bounds(
                left="0",
                bottom="0",
                right=decimal_text(Decimal(str(paper["width"])) * denominator),
                top=decimal_text(Decimal(str(paper["height"])) * denominator),
            ),
            paper_bounds_mm=Bounds(left="0", bottom="0", right="210", top="297"),
            layout_name=f"P{index:03d}_{row.values.code}",
        ),
        checks=DrawingChecks(
            bounds=CheckResult(passed=True, details=["exact B02 readback preflight required"]),
            collisions=CheckResult(passed=True, details=["full visible DXF cache preflight required"]),
            glyph_coverage=CheckResult(passed=True, details=["locked font preflight required"]),
        ),
    )


def _verified_page(page: DrawingPage, report: dict[str, Any]) -> DrawingPage:
    result = report["pages"][0]
    checks = DrawingChecks(
        bounds=CheckResult(
            passed=True,
            details=[
                "complete visible geometry inside controlled drawing area: "
                + str(result["geometry_lead_dimension_box_paper_mm"])
            ],
        ),
        collisions=CheckResult(
            passed=True,
            details=[
                "minimum lead/dimension clearance paper mm: "
                + format(result["lead_dimension_min_clearance_paper_mm"], ".9g")
            ],
        ),
        glyph_coverage=CheckResult(
            passed=True,
            details=[
                f"{len(result['text_measurements'])} editable template/field text records "
                "passed locked-font glyph and cell checks"
            ],
        ),
    )
    return page.model_copy(update={"checks": checks})


def _measured_bounds(page: DrawingPage, layout: dict) -> Bounds:
    factor = Decimal(page.scale.denominator)
    rectangle = page.geometry_mm.rectangle
    left = Decimal(rectangle.origin.x) / factor
    bottom = Decimal(rectangle.origin.y) / factor
    right = (Decimal(rectangle.origin.x) + Decimal(rectangle.width_mm)) / factor
    top = (Decimal(rectangle.origin.y) + Decimal(rectangle.length_mm)) / factor
    points = [
        (Decimal(segment.start.x) / factor, Decimal(segment.start.y) / factor)
        for segment in page.geometry_mm.lead_segments
    ] + [
        (Decimal(segment.end.x) / factor, Decimal(segment.end.y) / factor)
        for segment in page.geometry_mm.lead_segments
    ]
    placement = layout["dimension_placement_paper_mm"].get("sample_overrides", {}).get(
        page.code, layout["dimension_placement_paper_mm"]["fallback"]
    )
    padding = Decimal("3.5")
    return Bounds(
        left=decimal_text(min([left, *(p[0] for p in points)]) - Decimal(str(placement["length_offset"])) - padding),
        bottom=decimal_text(min([bottom, *(p[1] for p in points)]) - Decimal(str(placement["width_offset"])) - padding),
        right=decimal_text(max([right, *(p[0] for p in points)]) + Decimal(str(placement["length_offset"])) + padding),
        top=decimal_text(max([top, *(p[1] for p in points)]) + padding),
    )


def _proposal(row: HeaterRow, revision: Revision, template: dict, original_page: DrawingPage, proposed: Scale, reason: str) -> ScaleProposal:
    identity = f"{revision.revision_hash}:{row.row_id}:{original_page.scale.label}:{proposed.label}:{reason}"
    area = template["layout"]["drawing_area_mm"]
    return ScaleProposal(
        proposal_id=uuid5(PROPOSAL_NAMESPACE, identity),
        row_id=row.row_id,
        original=original_page.scale,
        proposed=proposed,
        reason=reason,
        measured_bounds_paper_mm=_measured_bounds(original_page, template["layout"]),
        available_bounds_paper_mm=Bounds(
            left=str(area["left"]), bottom=str(area["bottom"]),
            right=str(area["right"]), top=str(area["top"]),
        ),
        revision_hash=revision.revision_hash,
        template_hash=revision.template_hash,
    )


def _tile_pages(pages: list[DrawingPage]) -> tuple[DrawingPage, ...]:
    tiled: list[DrawingPage] = []
    cursor = Decimal("0")
    previous_factor: Decimal | None = None
    for page in pages:
        factor = Decimal(page.scale.denominator)
        if previous_factor is not None:
            cursor += Decimal("10") * max(previous_factor, factor)
        width = Decimal("210") * factor
        placement = page.placement.model_copy(
            update={
                "model_origin_mm": point(cursor, Decimal("0")),
                "tile_bounds_mm": Bounds(
                    left=decimal_text(cursor), bottom="0",
                    right=decimal_text(cursor + width),
                    top=decimal_text(Decimal("297") * factor),
                ),
            }
        )
        tiled.append(page.model_copy(update={"placement": placement}))
        cursor += width
        previous_factor = factor
    return tuple(tiled)


def _scale_acceptance_state(
    revision: Revision,
) -> tuple[tuple[ScaleProposal, ...], tuple[Issue, ...]]:
    """Return unresolved proposals and errors in scale-decision provenance."""

    proposals = {proposal.proposal_id: proposal for proposal in revision.proposals}
    resolved: set[UUID] = set()
    errors: list[Issue] = []
    row_by_id = {row.row_id: row for row in revision.rows}

    def invalid(row: HeaterRow, message: str) -> None:
        errors.append(_row_issue(row, f"比例确认关系无效：{message}"))

    proposal_ids = [proposal.proposal_id for proposal in revision.proposals]
    if len(proposal_ids) != len(set(proposal_ids)):
        for proposal in revision.proposals:
            row = row_by_id.get(proposal.row_id)
            if row is not None:
                invalid(row, "revision.proposals 含重复 proposal_id")

    original_scales = dict(revision.final_scales)
    proposal_base_hashes: set[str] = set()
    for proposal in revision.proposals:
        row = row_by_id.get(proposal.row_id)
        if row is None:
            continue
        existing = original_scales[proposal.row_id]
        if existing != revision.final_scales[proposal.row_id] and existing != proposal.original:
            invalid(row, "同一行的 proposal 原比例互相矛盾")
        original_scales[proposal.row_id] = proposal.original
        proposal_base_hashes.add(proposal.revision_hash)
    if revision.proposals:
        original_revision = revision.model_copy(update={"final_scales": original_scales})
        expected_base_hash = compute_revision_hash(original_revision)
        if proposal_base_hashes != {expected_base_hash}:
            for proposal in revision.proposals:
                row = row_by_id.get(proposal.row_id)
                if row is not None:
                    invalid(row, "proposal 未绑定由原比例重建的原修订 hash")

    for decision in revision.decisions:
        if decision.kind != DecisionKind.SCALE:
            continue
        decision_ids = decision.proposal_ids
        if (
            not decision_ids
            or len(decision_ids) != len(set(decision_ids))
            or not decision.row_ids
            or len(decision.row_ids) != len(set(decision.row_ids))
        ):
            for row_id in decision.row_ids:
                if row_id in row_by_id:
                    invalid(row_by_id[row_id], "scale decision 必须唯一列出 proposal 与行")
            continue
        selected = [proposals.get(proposal_id) for proposal_id in decision_ids]
        if any(proposal is None for proposal in selected):
            for row_id in decision.row_ids:
                if row_id in row_by_id:
                    invalid(row_by_id[row_id], "decision 引用了当前修订未携带的 proposal")
            continue
        selected_proposals = [proposal for proposal in selected if proposal is not None]
        proposal_rows = {proposal.row_id for proposal in selected_proposals}
        if proposal_rows != set(decision.row_ids):
            for row_id in proposal_rows | set(decision.row_ids):
                if row_id in row_by_id:
                    invalid(row_by_id[row_id], "decision 的 row_ids 与 proposal 行不一致")
            continue
        valid = True
        for proposal in selected_proposals:
            row = row_by_id.get(proposal.row_id)
            if row is None:
                valid = False
                continue
            final_scale = revision.final_scales[row.row_id]
            if proposal.proposal_id in resolved:
                invalid(row, "同一 proposal 被重复接受")
                valid = False
            if decision.base_revision_hash != proposal.revision_hash:
                invalid(row, "decision 未绑定 proposal 的原修订 hash")
                valid = False
            if proposal.template_hash != revision.template_hash:
                invalid(row, "proposal 未绑定当前受控模板")
                valid = False
            if proposal.original.label != row.values.requested_scale:
                invalid(row, "proposal 原比例与输入比例不一致")
                valid = False
            if proposal.proposed != final_scale:
                invalid(row, "最终比例与被接受 proposal 不一致")
                valid = False
        if valid:
            resolved.update(decision_ids)

    for row in revision.rows:
        requested = row.values.requested_scale
        final_scale = revision.final_scales[row.row_id]
        accepted = [
            proposal
            for proposal in revision.proposals
            if proposal.row_id == row.row_id and proposal.proposal_id in resolved
        ]
        if final_scale.label != requested and len(accepted) != 1:
            invalid(row, "输入比例与最终比例不同但没有唯一、有效的确认回执")
        if final_scale.label == requested and accepted:
            invalid(row, "确认的 proposal 未反映到最终比例")

    unresolved = tuple(
        proposal
        for proposal in revision.proposals
        if proposal.proposal_id not in resolved
    )
    return unresolved, tuple(errors)


def plan_pages(revision: Revision, template: dict | Path) -> PagePlan:
    """Return planned pages, errors and unconfirmed recommendations without mutating revision."""

    revision = validate_revision_hash(revision)
    controlled = (
        load_template(template)
        if isinstance(template, Path)
        else load_template(Path(template["directory"]))
    )
    controlled = output_template(controlled, revision.output_profile)
    if revision.template_hash != controlled["template_sha256"]:
        raise ValueError("revision template hash does not match the controlled template")
    if revision.template_version != controlled["manifest"]["version"]:
        raise ValueError("revision template version does not match the controlled template")
    if revision.font_manifest_hash != controlled["fonts_sha256"]:
        raise ValueError("revision font manifest hash does not match the controlled template")

    pending_proposals, decision_errors = _scale_acceptance_state(revision)
    skipped = set(revision.skipped_row_ids)
    covered_issue_ids = {
        issue_id
        for decision in revision.decisions
        if decision.kind == DecisionKind.SKIP
        for issue_id in decision.issue_ids
    }
    # Only explicitly covered, skippable row errors are removed from the drawing
    # gate. Warnings and workbook/system or non-skippable errors remain visible.
    inherited_issues = tuple(
        issue
        for issue in revision.issues
        if not (
            issue.severity == Severity.ERROR
            and issue.scope == IssueScope.ROW
            and issue.skippable
            and issue.row_id in skipped
            and issue.issue_id in covered_issue_ids
        )
    )
    initial_issues = (*inherited_issues, *decision_errors)
    if any(issue.severity == Severity.ERROR for issue in initial_issues):
        return PagePlan(
            revision_hash=revision.revision_hash,
            template_hash=revision.template_hash,
            expected_row_ids=tuple(revision.expected_row_ids),
            pages=(),
            issues=initial_issues,
            proposals=pending_proposals,
        )

    expected = set(revision.expected_row_ids)
    rows = [row for row in revision.rows if row.row_id in expected]
    pages: list[DrawingPage] = []
    issues: list[Issue] = list(initial_issues)
    proposals: list[ScaleProposal] = list(pending_proposals)
    diagnostics: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        original_scale = revision.final_scales[row.row_id]
        original_page = _page(row, revision, original_scale, controlled, index)
        passed, report, reason = preflight_page(original_page, controlled)
        diagnostics.append({
            "row_id": row.row_id,
            "scale": original_scale.label,
            "status": "passed" if passed else "failed",
            "reason": reason,
        })
        if passed:
            assert report is not None
            pages.append(_verified_page(original_page, report))
            continue
        assert reason is not None
        if not is_scale_sensitive(reason):
            field = "code" if "text" in reason or "glyph" in reason else "requested_scale"
            issues.append(_row_issue(row, f"排版预检失败：{reason}", field=field))
            continue

        recommended: Scale | None = None
        for denominator in recommendation_denominators(original_scale, controlled["layout"]):
            candidate_scale = make_scale(denominator)
            candidate = _page(row, revision, candidate_scale, controlled, index)
            candidate_passed, _, candidate_reason = preflight_page(candidate, controlled)
            diagnostics.append({
                "row_id": row.row_id,
                "scale": candidate_scale.label,
                "status": "passed" if candidate_passed else "failed",
                "reason": candidate_reason,
            })
            if candidate_passed:
                recommended = candidate_scale
                break
            if candidate_reason is not None and not is_scale_sensitive(candidate_reason):
                reason = candidate_reason
                break
        if recommended is None:
            issues.append(_row_issue(row, f"标准比例序列内无可行排版：{reason}"))
        else:
            proposals.append(
                _proposal(
                    row,
                    revision,
                    controlled,
                    original_page,
                    recommended,
                    "完整图元、尺寸箭头、文字、引线或禁入区在当前比例下不满足受控边界；建议最小可行比例",
                )
            )

    unique_proposals = tuple(
        {proposal.proposal_id: proposal for proposal in proposals}.values()
    )
    return PagePlan(
        revision_hash=revision.revision_hash,
        template_hash=revision.template_hash,
        expected_row_ids=tuple(revision.expected_row_ids),
        pages=_tile_pages(pages),
        issues=tuple(issues),
        proposals=unique_proposals,
        diagnostics=tuple(diagnostics),
    )
