#!/usr/bin/env python3
"""Plan and export the real B04 workbook through the production drawing path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid5, UUID

from heater_drawing.domain.models import Revision, Scale, Severity
from heater_drawing.drawing.dxf_writer import (
    export_planned_dxf,
    write_page_dxf,
)
from heater_drawing.drawing.fonts import prepare_runtime_font
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.pdf_renderer import render_page
from heater_drawing.drawing.template import load_template
from heater_drawing.excel import parse_workbook, validate_rows


REVISION_NAMESPACE = UUID("3dc32c03-2bad-47d6-a235-b4a4d79ba4b7")


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _revision(source: Path, template: dict) -> tuple[Revision | None, list]:
    parsed = parse_workbook(source)
    validated = validate_rows(parsed.rows, template)
    issues = [*parsed.issues, *validated.issues]
    if any(issue.severity == Severity.ERROR for issue in issues):
        return None, issues
    if len(validated.source_rows) != len(parsed.rows) or len(validated.rows) != len(parsed.rows):
        raise ValueError("validated rows do not cover every source row")
    final_scales = {}
    for row in validated.rows:
        denominator = row.values.requested_scale.split(":", 1)[1]
        final_scales[row.row_id] = Scale(
            denominator=denominator, label=row.values.requested_scale
        )
    identity = f"{parsed.source_sha256}:{template['template_sha256']}"
    return Revision.create(
        revision_id=uuid5(REVISION_NAMESPACE, identity),
        parent_revision_id=None,
        source_sha256=parsed.source_sha256,
        template_version=template["manifest"]["version"],
        template_hash=template["template_sha256"],
        font_manifest_hash=template["fonts_sha256"],
        output_profile="dxf_pdf_v1",
        rows=list(validated.rows),
        final_scales=final_scales,
        issues=issues,
        proposals=[],
        decisions=[],
        skipped_row_ids=[],
        expected_row_ids=[row.row_id for row in validated.rows],
    ), issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    template = load_template(args.template)
    revision, import_issues = _revision(args.input, template)
    if revision is None:
        _json(output / "plan.json", {
            "schema_version": 1,
            "status": "invalid_input",
            "diagnostic_only": True,
            "issues": [issue.model_dump(mode="json") for issue in import_issues],
            "artifacts": [],
        })
        return 1

    plan = plan_pages(revision, template)
    _json(output / "plan.json", {
        "schema_version": 1,
        "status": "ready" if plan.exportable else "awaiting_resolution",
        "diagnostic_only": not plan.exportable,
        "revision_hash": revision.revision_hash,
        "issues": [issue.model_dump(mode="json") for issue in plan.issues],
        "proposals": [proposal.model_dump(mode="json") for proposal in plan.proposals],
        "diagnostics": list(plan.diagnostics),
        "artifacts": ["加热器图纸.dxf"] if plan.exportable else [],
    })
    _json(output / "pages.json", {
        "schema_version": 1,
        "revision_hash": revision.revision_hash,
        "template_hash": revision.template_hash,
        "page_order": [page.row_id for page in plan.pages],
        "layout_mapping": [
            {"page_index": index, "row_id": page.row_id, "code": page.code,
             "layout_name": page.placement.layout_name, "scale": page.scale.label}
            for index, page in enumerate(plan.pages, start=1)
        ],
        "pages": [page.model_dump(mode="json") for page in plan.pages],
    })
    if not plan.exportable:
        return 2

    combined = output / "加热器图纸.dxf"
    export_planned_dxf(combined, plan, revision, template)
    font = prepare_runtime_font(template["fonts"], Path(__file__).resolve().parents[1])
    renders = []
    for page in plan.pages:
        page_dxf = output / "diagnostics" / f"{page.code}.dxf"
        page_pdf = output / "diagnostics" / f"{page.code}.diagnostic.pdf"
        page_png = output / "diagnostics" / f"{page.code}.diagnostic.png"
        write_page_dxf(
            page_dxf, page, template["layout"], template["fonts"],
            template_path=template["directory"] / "template.dxf",
        )
        render = render_page(
            page_dxf, page_pdf, page_png, float(page.scale.denominator),
            font, template["fonts"],
        )
        renders.append({
            "row_id": page.row_id,
            "code": page.code,
            "classification": "development_diagnostic_not_artifact",
            "dxf": str(page_dxf.relative_to(output)),
            "png": str(page_png.relative_to(output)),
            "pdf": str(page_pdf.relative_to(output)),
            "render": render,
        })
    _json(output / "diagnostics" / "manifest.json", {
        "schema_version": 1,
        "classification": "development_diagnostic_not_artifact",
        "pages": renders,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
