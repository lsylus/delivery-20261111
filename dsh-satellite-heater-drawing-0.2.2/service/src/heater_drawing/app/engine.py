"""Process-isolated adapters around the verified drawing/delivery engine."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from heater_drawing.domain.models import Decision, DecisionKind, Revision, Scale, Severity
from heater_drawing.drawing.dxf_writer import export_planned_dxf
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.profile import NATIVE_PROFILE
from heater_drawing.drawing.template import load_template
from heater_drawing.excel import parse_workbook, validate_rows
from heater_drawing.delivery.package import build_delivery


def dump(value):
    return value.model_dump(mode="json")


def snapshot(revision, plan, total):
    unresolved = [dump(p) for p in plan.proposals]
    issues = [dump(i) for i in plan.issues]
    return {"revision": dump(revision), "issues": issues, "proposals": unresolved,
            "exportable": plan.exportable, "total_rows": total,
            "expected_pages": len(revision.expected_row_ids),
            "skipped_rows": revision.skipped_row_ids,
            "rows": [{"row_id": r.row_id, "code": r.values.code,
                      "name": r.values.name, "scale": revision.final_scales[r.row_id].label}
                     for r in revision.rows]}


def analyze(source, template_dir):
    template = load_template(template_dir)
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows, template)
    issues = [*parsed.issues, *validated.issues]
    # Never construct plausible replacement values for malformed Excel rows.
    if any(i.severity == Severity.ERROR for i in issues) or not validated.rows:
        return {"revision": None, "issues": [dump(i) for i in issues],
                "proposals": [], "exportable": False, "total_rows": len(parsed.rows),
                "expected_pages": 0, "skipped_rows": [], "rows": [],
                "requires_reupload": True}
    revision = Revision.create(
        revision_id=uuid4(), parent_revision_id=None, source_sha256=parsed.source_sha256,
        template_version=template["manifest"]["version"], template_hash=template["template_sha256"],
        font_manifest_hash=template["fonts_sha256"], output_profile=NATIVE_PROFILE,
        rows=list(validated.rows), final_scales={r.row_id: Scale(
            denominator=r.values.requested_scale.split(":")[1], label=r.values.requested_scale)
            for r in validated.rows}, issues=issues, proposals=[], decisions=[],
        skipped_row_ids=[], expected_row_ids=[r.row_id for r in validated.rows])
    plan = plan_pages(revision, template)
    # Store the exact issues and proposals shown to the user, without altering
    # the content hash (these are derived data, as defined in C02.3).
    data = dump(revision)
    data.update(issues=[dump(i) for i in plan.issues], proposals=[dump(p) for p in plan.proposals])
    data.pop("revision_hash")
    revision = Revision.create(**data)
    return snapshot(revision, plan, len(parsed.rows))


def decide(current, selection, actor, receipt_id, template_dir):
    revision = Revision.model_validate(current["revision"])
    data = dump(revision)
    data.pop("revision_hash")
    data.update(revision_id=uuid4(), parent_revision_id=revision.revision_id)
    kind = selection["kind"]
    decision = Decision(
        decision_id=uuid4(), actor_id=actor, decided_at=datetime.now(timezone.utc),
        kind=kind, base_revision_hash=revision.revision_hash,
        reason=selection["reason"], confirmation_receipt_id=receipt_id,
        row_ids=selection.get("row_ids", []),
        issue_ids=selection.get("issue_ids", []), proposal_ids=selection.get("proposal_ids", []))
    if kind == "scale":
        if set(selection["proposal_ids"]) != {p["proposal_id"] for p in current["proposals"]}:
            raise ValueError("请一次选择本次全部待确认比例；不接受的比例请修改 Excel 后重新上传")
        selected = {str(p.proposal_id): p for p in revision.proposals
                    if str(p.proposal_id) in selection["proposal_ids"]}
        if set(selected) != set(selection["proposal_ids"]) or not selected:
            raise ValueError("比例建议已失效，请刷新")
        if set(selection["row_ids"]) != {p.row_id for p in selected.values()}:
            raise ValueError("比例行集合与建议不一致")
        if any(d.kind == DecisionKind.SCALE for d in revision.decisions):
            raise ValueError("请一次选择本次需要接受的全部比例，或修正 Excel 重传")
        for proposal in selected.values():
            data["final_scales"][proposal.row_id] = dump(proposal.proposed)
        data["decisions"].append(dump(decision))
    elif kind == "skip":
        selected = {str(i.issue_id): i for i in revision.issues
                    if str(i.issue_id) in selection["issue_ids"]}
        if not selected or set(selected) != set(selection["issue_ids"]):
            raise ValueError("问题集合已失效，请刷新")
        rows = set(selection["row_ids"])
        if rows != {i.row_id for i in selected.values()} or any(
                not i.skippable or i.scope.value != "row" for i in selected.values()):
            raise ValueError("只能跳过列明问题的指定行")
        if rows & set(revision.skipped_row_ids):
            raise ValueError("该行已跳过")
        skipped = set(revision.skipped_row_ids) | rows
        data["skipped_row_ids"] = [r.row_id for r in revision.rows if r.row_id in skipped]
        data["expected_row_ids"] = [r.row_id for r in revision.rows if r.row_id not in skipped]
        if not data["expected_row_ids"]:
            raise ValueError("不能跳过全部行")
        data["final_scales"] = {r.row_id: dump(Scale(
            denominator=r.values.requested_scale.split(":")[1], label=r.values.requested_scale))
            for r in revision.rows}
        data["decisions"] = [dump(d) for d in revision.decisions if d.kind == DecisionKind.SKIP] + [dump(decision)]
        data["proposals"] = []
    else:
        raise ValueError("不支持的确认类型")
    updated = Revision.create(**data)
    plan = plan_pages(updated, load_template(template_dir))
    data = dump(updated)
    data.pop("revision_hash")
    data["issues"] = [dump(i) for i in plan.issues] + [
        dump(i) for i in revision.issues if i.row_id in updated.skipped_row_ids]
    data["proposals"] = [dump(p) for p in plan.proposals] if kind == "skip" else data["proposals"]
    updated = Revision.create(**data)
    return snapshot(updated, plan, current["total_rows"])


def generate(source, revision_file, template_dir, output, package_name):
    revision = Revision.model_validate_json(revision_file.read_text())
    template = load_template(template_dir)
    plan = plan_pages(revision, template)
    if not plan.exportable:
        raise ValueError("修订仍有错误或未确认比例")
    dxf, pages = output.parent / "input.dxf", output.parent / "pages.json"
    export_planned_dxf(dxf, plan, revision, template)
    pages.write_text(json.dumps({
        "schema_version": 1, "revision_hash": revision.revision_hash,
        "template_hash": revision.template_hash, "page_order": list(plan.expected_row_ids),
        "layout_mapping": [{"page_index": index, "row_id": page.row_id, "code": page.code,
                            "layout_name": page.placement.layout_name, "scale": page.scale.label}
                           for index, page in enumerate(plan.pages, 1)],
        "pages": [dump(page) for page in plan.pages]}, ensure_ascii=False))
    return build_delivery(revision, input_dxf=dxf, pages_path=pages,
                          original_workbook=source, output=output,
                          template_dir=template_dir, package_name=package_name)
