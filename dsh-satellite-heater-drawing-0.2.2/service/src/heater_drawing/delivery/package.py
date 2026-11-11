"""Build a B05 candidate from one frozen revision and one formal DXF mapping."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from heater_drawing.domain.models import (
    DecisionKind,
    IssueScope,
    Revision,
    Severity,
    validate_revision_hash,
)
from heater_drawing.drawing.dxf_writer import export_planned_dxf
from heater_drawing.drawing.fonts import prepare_runtime_font
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.pdf_renderer import render_page
from heater_drawing.drawing.readback import inspect_dxf
from heater_drawing.drawing.template import load_template
from heater_drawing.drawing.opencadstudio import PROFILE as NATIVE_PROFILE, export_dwg_pdf
from heater_drawing.drawing.profile import output_template

from .manifest import artifact_entry, sha256_file, write_json
from .pdf_merge import merge_single_page_pdfs
from .validation import DeliveryError, row_report_contract, validate_delivery
from .workbooks import build_workbooks


def _row_report(revision: Revision) -> dict[str, Any]:
    """Backward-compatible internal name used by existing audit evidence."""

    return row_report_contract(revision)


def _bound_pages(path: Path, revision: Revision, planned) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryError("PAGE_BINDING_MISMATCH", f"cannot read pages mapping: {exc}") from exc
    expected = [page.model_dump(mode="json") for page in planned.pages]
    if (
        value.get("revision_hash") != revision.revision_hash
        or value.get("template_hash") != revision.template_hash
        or value.get("page_order") != revision.expected_row_ids
        or value.get("pages") != expected
    ):
        raise DeliveryError(
            "PAGE_BINDING_MISMATCH",
            "pages mapping does not exactly match the frozen revision and fresh plan",
        )
    expected_mapping = [
        {
            "page_index": index,
            "row_id": page.row_id,
            "code": page.code,
            "layout_name": page.placement.layout_name,
            "scale": page.scale.label,
        }
        for index, page in enumerate(planned.pages, start=1)
    ]
    if value.get("layout_mapping") != expected_mapping:
        raise DeliveryError("PAGE_BINDING_MISMATCH", "layout mapping differs from page order")
    return value


def build_delivery(
    revision: Revision | dict[str, Any],
    *,
    input_dxf: Path,
    pages_path: Path,
    original_workbook: Path,
    output: Path,
    template_dir: Path,
    package_name: str = "heater-drawings",
) -> dict[str, Any]:
    """Build and validate an isolated candidate; never replace an existing target."""

    revision = validate_revision_hash(revision)
    if (
        not package_name
        or len(package_name) > 128
        or any(character in package_name for character in "/\\\r\n\0")
        or package_name in {".", ".."}
    ):
        raise DeliveryError("PATH_ESCAPE", "package name is unsafe")
    covered_issue_ids = {
        issue_id
        for decision in revision.decisions
        if decision.kind == DecisionKind.SKIP
        for issue_id in decision.issue_ids
    }
    skipped = set(revision.skipped_row_ids)
    if any(
        issue.severity == Severity.ERROR
        and not (
            issue.scope == IssueScope.ROW
            and issue.skippable
            and issue.row_id in skipped
            and issue.issue_id in covered_issue_ids
        )
        for issue in revision.issues
    ):
        raise DeliveryError("UNRESOLVED_ERROR", "revision retains one or more error issues")
    if not revision.expected_row_ids:
        raise DeliveryError("EMPTY_DELIVERY_SET", "all-skip delivery is forbidden")
    if output.exists():
        raise DeliveryError("OUTPUT_EXISTS", f"candidate target already exists: {output}")
    if sha256_file(original_workbook) != revision.source_sha256:
        raise DeliveryError("INPUT_HASH_MISMATCH", "source workbook hash differs from revision")
    controlled = output_template(load_template(template_dir), revision.output_profile)
    planned = plan_pages(revision, controlled)
    if not planned.exportable:
        code = "UNACCEPTED_PROPOSAL" if planned.proposals else "UNRESOLVED_ERROR"
        raise DeliveryError(code, "frozen revision is not exportable")
    _bound_pages(pages_path, revision, planned)
    try:
        inspect_dxf(
            input_dxf,
            list(planned.pages),
            controlled["layout"],
            controlled["fonts"],
        )
    except Exception as exc:
        raise DeliveryError("DXF_READBACK_FAILED", f"input DXF failed fresh readback: {exc}") from exc

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid4())
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-candidate-", dir=output.parent) as value:
        root = Path(value) / "package"
        root.mkdir()
        formal_dxf = root / f"{package_name}.dxf"
        export_planned_dxf(formal_dxf, planned, revision, controlled)
        source_dxf_sha256 = sha256_file(input_dxf)
        formal_dxf_sha256 = sha256_file(formal_dxf)
        render_scratch = root / ".render"
        render_scratch.mkdir()
        single_pdfs: list[Path] = []
        render_reports: list[dict[str, Any]] = []
        native = revision.output_profile == NATIVE_PROFILE
        if native:
            try:
                cad_report = export_dwg_pdf(
                    formal_dxf, root / f"{package_name}.dwg", planned.pages,
                    controlled, root / "pdf",
                )
            except Exception as exc:
                raise DeliveryError("NATIVE_CAD_FAILED", str(exc)) from exc
            write_json(root / "cad-report.json", cad_report)
            write_json(root / "revision.json", revision.model_dump(mode="json"))
            render_reports = cad_report["render_reports"]
            single_pdfs = [root / "pdf" / f"{page.code}.pdf" for page in planned.pages]
        else:
            font = prepare_runtime_font(controlled["fonts"], Path(__file__).resolve().parents[4])
            for index, page in enumerate(planned.pages, start=1):
                pdf = root / "pdf" / f"{page.code}.pdf"
                png = render_scratch / f"{index:03d}-{page.code}.png"
                report = render_page(
                    formal_dxf, pdf, png, float(page.scale.denominator), font,
                    controlled["fonts"],
                    model_origin_mm=(float(page.placement.model_origin_mm.x),
                                     float(page.placement.model_origin_mm.y)),
                )
                report.update({"row_id": page.row_id, "code": page.code, "page_index": index})
                render_reports.append(report)
                single_pdfs.append(pdf)
        merged = root / f"{package_name}.pdf"
        merge_single_page_pdfs(single_pdfs, merged)
        shutil.rmtree(render_scratch)
        original, actual = build_workbooks(revision, original_workbook, root)
        report_path = root / "row-report.json"
        write_json(report_path, row_report_contract(revision))

        files = [
            artifact_entry(
                root, formal_dxf, run_id=run_id, revision_hash=revision.revision_hash,
                kind="dxf", media_type="image/vnd.dxf",
                row_ids=revision.expected_row_ids,
            ),
        ]
        if native:
            files.extend([
                artifact_entry(root, root / f"{package_name}.dwg", run_id=run_id,
                               revision_hash=revision.revision_hash, kind="dwg",
                               media_type="image/vnd.dwg", row_ids=revision.expected_row_ids),
                artifact_entry(root, root / "cad-report.json", run_id=run_id,
                               revision_hash=revision.revision_hash, kind="report",
                               media_type="application/json", row_ids=revision.expected_row_ids),
                artifact_entry(root, root / "revision.json", run_id=run_id,
                               revision_hash=revision.revision_hash, kind="report",
                               media_type="application/json", row_ids=[row.row_id for row in revision.rows]),
            ])
        for index, (page, pdf) in enumerate(zip(planned.pages, single_pdfs, strict=True), start=1):
            files.append(artifact_entry(
                root, pdf, run_id=run_id, revision_hash=revision.revision_hash,
                kind="pdf_single", media_type="application/pdf", row_ids=[page.row_id],
                page_count=1, page_index=index,
            ))
        files.extend([
            artifact_entry(
                root, merged, run_id=run_id, revision_hash=revision.revision_hash,
                kind="pdf_merged", media_type="application/pdf",
                row_ids=revision.expected_row_ids, page_count=len(single_pdfs),
            ),
            artifact_entry(
                root, original, run_id=run_id, revision_hash=revision.revision_hash,
                kind="excel_original",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                row_ids=[row.row_id for row in revision.rows],
            ),
            artifact_entry(
                root, actual, run_id=run_id, revision_hash=revision.revision_hash,
                kind="excel_actual",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                row_ids=revision.expected_row_ids,
            ),
            artifact_entry(
                root, report_path, run_id=run_id, revision_hash=revision.revision_hash,
                kind="report", media_type="application/json",
                row_ids=[row.row_id for row in revision.rows],
            ),
        ])
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "revision_id": str(revision.revision_id),
            "revision_hash": revision.revision_hash,
            "source_sha256": revision.source_sha256,
            "template_version": revision.template_version,
            "template_hash": revision.template_hash,
            "font_manifest_hash": revision.font_manifest_hash,
            "output_profile": revision.output_profile,
            "package_name": package_name,
            "expected_row_ids": revision.expected_row_ids,
            "skipped_row_ids": revision.skipped_row_ids,
            "page_mapping": [
                {"page_index": index, "row_id": page.row_id, "code": page.code,
                 "relative_path": f"pdf/{page.code}.pdf"}
                for index, page in enumerate(planned.pages, start=1)
            ],
            "input_bindings": {
                "input_dxf_sha256": source_dxf_sha256,
                "formal_dxf_sha256": formal_dxf_sha256,
                "pages_sha256": sha256_file(pages_path),
                "original_workbook_sha256": sha256_file(original_workbook),
            },
            "render_reports": render_reports,
            "formats": {
                "dxf": {"status": "provided", "artifacts": [f"{package_name}.dxf"]},
                "pdf": {"status": "provided", "artifacts": [
                    *[f"pdf/{page.code}.pdf" for page in planned.pages], f"{package_name}.pdf"
                ]},
                "dwg": ({"status": "provided", "artifacts": [f"{package_name}.dwg"]}
                        if native else {"status": "disabled_not_provided", "artifacts": []}),
            },
            "files": files,
        }
        manifest_path = root / "manifest.json"
        write_json(manifest_path, manifest)
        zip_path = root / f"{package_name}.zip"
        members = sorted([item["relative_path"] for item in files] + ["manifest.json"])
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative in members:
                archive.write(root / relative, relative)
        run = {
            "schema_version": 1,
            "run_id": run_id,
            "revision_id": str(revision.revision_id),
            "revision_hash": revision.revision_hash,
            "state": "verified_candidate",
            "expected_row_ids": revision.expected_row_ids,
            "manifest": {
                "relative_path": "manifest.json",
                "sha256": sha256_file(manifest_path),
                "bytes": manifest_path.stat().st_size,
            },
            "zip": {
                "relative_path": zip_path.name,
                "sha256": sha256_file(zip_path),
                "bytes": zip_path.stat().st_size,
            },
        }
        write_json(root / "run.json", run)
        result = validate_delivery(root, revision, template_dir=template_dir)
        root.replace(output)
    return result
