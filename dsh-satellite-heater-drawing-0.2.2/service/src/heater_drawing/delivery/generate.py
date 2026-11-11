"""One-step Excel/template to verified native DWG and PDF delivery."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from uuid import uuid4

from heater_drawing.domain.models import Revision, Scale, Severity
from heater_drawing.drawing.dxf_writer import export_planned_dxf
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.opencadstudio import PROFILE, font_paths, resolve_executable
from heater_drawing.drawing.profile import output_template
from heater_drawing.drawing.template import load_template
from heater_drawing.excel import parse_workbook, validate_rows
from .package import build_delivery
from .validation import DeliveryError


def generate_from_excel(
    source: Path, *, template_dir: Path, output: Path, package_name="加热器图纸",
) -> dict:
    """Respect Excel values and requested scales; never silently drop or resize rows."""
    if output.exists():
        raise DeliveryError("OUTPUT_EXISTS", f"target already exists: {output}")
    template = load_template(template_dir)
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows, template)
    issues = [*parsed.issues, *validated.issues]
    errors = [issue for issue in issues if issue.severity == Severity.ERROR]
    if errors:
        raise DeliveryError("INVALID_INPUT", json.dumps(
            [issue.model_dump(mode="json") for issue in errors], ensure_ascii=False,
        ))
    revision = Revision.create(
        revision_id=uuid4(), parent_revision_id=None,
        source_sha256=parsed.source_sha256,
        template_version=template["manifest"]["version"],
        template_hash=template["template_sha256"],
        font_manifest_hash=template["fonts_sha256"], output_profile=PROFILE,
        rows=list(validated.rows),
        final_scales={row.row_id: Scale(
            denominator=row.values.requested_scale.split(":", 1)[1],
            label=row.values.requested_scale,
        ) for row in validated.rows},
        issues=issues, proposals=[], decisions=[], skipped_row_ids=[],
        expected_row_ids=[row.row_id for row in validated.rows],
    )
    try:
        resolve_executable()
        font_paths(output_template(template, PROFILE))
    except (OSError, ValueError) as exc:
        raise DeliveryError("NATIVE_CAD_FAILED", str(exc)) from exc
    plan = plan_pages(revision, template)
    if not plan.exportable:
        raise DeliveryError("UNRESOLVED_ERROR", json.dumps({
            "issues": [issue.model_dump(mode="json") for issue in plan.issues],
            "proposals": [proposal.model_dump(mode="json") for proposal in plan.proposals],
        }, ensure_ascii=False))
    with tempfile.TemporaryDirectory(prefix="heater-generate-") as folder:
        root = Path(folder)
        dxf, pages = root / "source.dxf", root / "pages.json"
        export_planned_dxf(dxf, plan, revision, template)
        pages.write_text(json.dumps({
            "schema_version": 1, "revision_hash": revision.revision_hash,
            "template_hash": revision.template_hash,
            "page_order": list(plan.expected_row_ids),
            "layout_mapping": [
                {"page_index": index, "row_id": page.row_id, "code": page.code,
                 "layout_name": page.placement.layout_name, "scale": page.scale.label}
                for index, page in enumerate(plan.pages, start=1)
            ],
            "pages": [page.model_dump(mode="json") for page in plan.pages],
        }, ensure_ascii=False), encoding="utf-8")
        result = build_delivery(
            revision, input_dxf=dxf, pages_path=pages, original_workbook=source,
            output=output, template_dir=template_dir, package_name=package_name,
        )
    return {**result, "output": str(output.resolve()), "output_profile": PROFILE}
