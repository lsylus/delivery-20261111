"""Fail-closed validation for a complete B05 delivery candidate."""

from __future__ import annotations

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

import pymupdf
from openpyxl import load_workbook
from pypdf import PdfReader

from heater_drawing.domain.models import (
    Artifact,
    ArtifactKind,
    DecisionKind,
    Revision,
    validate_revision_hash,
)
from heater_drawing.drawing.fonts import prepare_runtime_font
from heater_drawing.drawing.layout import plan_pages
from heater_drawing.drawing.pdf_renderer import render_page
from heater_drawing.drawing.readback import inspect_dxf
from heater_drawing.drawing.template import load_template
from heater_drawing.drawing.profile import output_template
from heater_drawing.drawing.opencadstudio import (
    PROFILE as NATIVE_PROFILE, SAMPLE_PRINT_SCALE, plot_options, verify_dwg_pdf,
)
from heater_drawing.excel import parse_workbook, validate_rows

from .manifest import sha256_file


@dataclass(slots=True)
class DeliveryError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _fail(code: str, message: str) -> None:
    raise DeliveryError(code, message)


def _safe_path(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if (
        value.is_absolute()
        or not value.parts
        or any(part in {"", ".", ".."} for part in value.parts)
        or "\\" in relative
    ):
        _fail("PATH_ESCAPE", f"unsafe artifact path: {relative!r}")
    target = root.joinpath(*value.parts)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        _fail("PATH_ESCAPE", f"artifact leaves candidate directory: {relative!r}")
    return target


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(code, f"cannot read {path.name}: {exc}")
    if not isinstance(value, dict):
        _fail(code, f"{path.name} must contain a JSON object")
    return value


def _pdf(path: Path, expected_pages: int) -> PdfReader:
    try:
        reader = PdfReader(str(path), strict=True)
        actual = len(reader.pages)
    except Exception as exc:
        _fail("INVALID_PDF", f"cannot read {path.name}: {exc}")
    if actual != expected_pages:
        _fail(
            "PAGE_COUNT_MISMATCH",
            f"{path.name} has {actual} pages, expected {expected_pages}",
        )
    for index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width) * 25.4 / 72.0
        height = float(page.mediabox.height) * 25.4 / 72.0
        if abs(width - 210.0) > 0.2 or abs(height - 297.0) > 0.2:
            _fail(
                "PAGE_SIZE_MISMATCH",
                f"{path.name} page {index} is {width:.3f} x {height:.3f} mm",
            )
    return reader


def _rendered_page_bytes(path: Path, index: int = 0) -> tuple[int, int, bytes]:
    try:
        with pymupdf.open(path) as document:
            pixmap = document[index].get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False)
            return pixmap.width, pixmap.height, bytes(pixmap.samples)
    except Exception as exc:
        _fail("INVALID_PDF", f"cannot render {path.name} page {index + 1}: {exc}")


def row_report_contract(revision: Revision) -> dict[str, Any]:
    """Return the exact row/global issue trace required in a B05 report."""

    rows: list[dict[str, Any]] = []
    for row in revision.rows:
        skip = next(
            (
                decision
                for decision in revision.decisions
                if decision.kind == DecisionKind.SKIP
                and row.row_id in decision.row_ids
            ),
            None,
        )
        final_values = row.values.model_dump(mode="json")
        final_values["requested_scale"] = revision.final_scales[row.row_id].label
        rows.append(
            {
                "row_id": row.row_id,
                "source": row.source.model_dump(mode="json"),
                "code": row.values.code,
                "status": (
                    "skipped"
                    if row.row_id in revision.skipped_row_ids
                    else "delivered"
                ),
                "input_values": row.values.model_dump(mode="json"),
                "final_values": final_values,
                "issues": [
                    issue.model_dump(mode="json")
                    for issue in revision.issues
                    if issue.row_id == row.row_id
                ],
                "skip": (
                    None
                    if skip is None
                    else {
                        "reason": skip.reason,
                        "actor_id": skip.actor_id,
                        "decided_at": skip.decided_at.isoformat(),
                        "confirmation_receipt_id": skip.confirmation_receipt_id,
                        "issue_ids": [str(value) for value in skip.issue_ids],
                    }
                ),
            }
        )
    return {
        "schema_version": 1,
        "revision_id": str(revision.revision_id),
        "revision_hash": revision.revision_hash,
        "expected_row_ids": revision.expected_row_ids,
        "skipped_row_ids": revision.skipped_row_ids,
        "global_issues": [
            issue.model_dump(mode="json")
            for issue in revision.issues
            if issue.row_id is None
        ],
        "rows": rows,
    }


def _normalized_datetime(value: Any, *, row_id: str) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            _fail("INVALID_WORKBOOK", f"actual.xlsx time is invalid for {row_id}")
    else:
        _fail("INVALID_WORKBOOK", f"actual.xlsx time has invalid type for {row_id}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("INVALID_WORKBOOK", f"actual.xlsx time lacks a timezone for {row_id}")
    return parsed


def _validate_controlled_workbook_cell_types(path: Path) -> None:
    workbook = load_workbook(path, data_only=False, read_only=False)
    try:
        if workbook.sheetnames != ["Sheet1", "变更记录"]:
            _fail("INVALID_WORKBOOK", "actual.xlsx sheet collection is not controlled")
        for sheet in workbook.worksheets:
            for cells in sheet.iter_rows():
                for cell in cells:
                    if cell.data_type == "f":
                        _fail(
                            "INVALID_WORKBOOK",
                            "actual.xlsx formulas are forbidden: "
                            f"{sheet.title}!{cell.coordinate}",
                        )
    finally:
        workbook.close()


def _validate_workbooks(root: Path, revision: Revision) -> None:
    original = root / "original.xlsx"
    if sha256_file(original) != revision.source_sha256:
        _fail("INPUT_HASH_MISMATCH", "original.xlsx does not preserve the frozen source bytes")
    actual_path = root / "actual.xlsx"
    _validate_controlled_workbook_cell_types(actual_path)
    parsed = parse_workbook(actual_path)
    validated = validate_rows(parsed.rows)
    if parsed.has_errors or validated.has_errors:
        _fail("INVALID_WORKBOOK", "actual.xlsx does not satisfy the 17-field contract")
    expected_rows = [
        row for row in revision.rows if row.row_id in set(revision.expected_row_ids)
    ]
    if len(validated.rows) != len(expected_rows):
        _fail("ROW_SET_MISMATCH", "actual.xlsx delivered row count differs from revision")
    for actual, expected in zip(validated.rows, expected_rows, strict=True):
        values = actual.values.model_dump(mode="json")
        wanted = expected.values.model_dump(mode="json")
        wanted["requested_scale"] = revision.final_scales[expected.row_id].label
        if values != wanted:
            _fail("INVALID_WORKBOOK", f"actual.xlsx values differ for {expected.row_id}")

    workbook = load_workbook(actual_path, data_only=False, read_only=True)
    try:
        if workbook.sheetnames != ["Sheet1", "变更记录"]:
            _fail("INVALID_WORKBOOK", "actual.xlsx sheet collection is not controlled")
        changes = workbook["变更记录"]
        expected_headers = (
            "row_id",
            "原Excel行",
            "状态",
            "原比例",
            "最终比例",
            "跳过原因",
            "确认者",
            "确认时间",
            "确认回执",
            "revision_hash",
        )
        headers = tuple(
            cell.value for cell in next(changes.iter_rows(min_row=1, max_row=1))
        )
        if headers != expected_headers or changes.max_column != len(expected_headers):
            _fail("INVALID_WORKBOOK", "actual.xlsx change log columns differ")
        rows = list(changes.iter_rows(min_row=2, values_only=True))
        if len(rows) != len(revision.rows) or [row[0] for row in rows] != [
            row.row_id for row in revision.rows
        ]:
            _fail("ROW_SET_MISMATCH", "actual.xlsx change log does not cover source rows in order")
        for record, source in zip(rows, revision.rows, strict=True):
            matching = [
                decision
                for decision in revision.decisions
                if source.row_id in decision.row_ids
            ]
            skip = next(
                (item for item in matching if item.kind == DecisionKind.SKIP), None
            )
            scale = next(
                (item for item in matching if item.kind == DecisionKind.SCALE), None
            )
            decision = skip or scale
            expected = (
                source.row_id,
                str(source.source.excel_row),
                (
                    "skipped"
                    if source.row_id in revision.skipped_row_ids
                    else "delivered"
                ),
                source.values.requested_scale,
                revision.final_scales[source.row_id].label,
                skip.reason if skip else "",
                decision.actor_id if decision else "",
                decision.confirmation_receipt_id if decision else "",
                revision.revision_hash,
            )
            actual_without_time = tuple(
                "" if value is None else value
                for value in (*record[:7], *record[8:10])
            )
            if actual_without_time != expected:
                _fail(
                    "INVALID_WORKBOOK",
                    f"actual.xlsx change trace differs for {source.row_id}",
                )
            actual_time = _normalized_datetime(record[7], row_id=source.row_id)
            expected_time = decision.decided_at if decision else None
            if actual_time != expected_time:
                _fail(
                    "INVALID_WORKBOOK",
                    f"actual.xlsx decision time differs for {source.row_id}",
                )
    finally:
        workbook.close()


def _validate_report(root: Path, revision: Revision) -> None:
    report = _load_json(root / "row-report.json", "INVALID_REPORT")
    if report != row_report_contract(revision):
        _fail("INVALID_REPORT", "row report does not exactly match the frozen revision")


def validate_delivery(
    directory: Path,
    revision: Revision | dict[str, Any],
    *,
    template_dir: Path,
) -> dict[str, Any]:
    """Validate exact files, hashes, page mapping, workbooks and the ZIP."""

    root = directory.resolve()
    revision = validate_revision_hash(revision)
    native = revision.output_profile == NATIVE_PROFILE
    if not root.is_dir():
        _fail("MISSING_ARTIFACT", f"candidate directory does not exist: {root}")
    if any(path.is_symlink() for path in root.rglob("*")):
        _fail("PATH_ESCAPE", "candidate must not contain symbolic links")
    manifest_path = root / "manifest.json"
    run_path = root / "run.json"
    manifest = _load_json(manifest_path, "INVALID_MANIFEST")
    run = _load_json(run_path, "INVALID_RUN_RECORD")
    manifest_keys = {
        "schema_version",
        "run_id",
        "revision_id",
        "revision_hash",
        "source_sha256",
        "template_version",
        "template_hash",
        "font_manifest_hash",
        "output_profile",
        "package_name",
        "expected_row_ids",
        "skipped_row_ids",
        "page_mapping",
        "input_bindings",
        "render_reports",
        "formats",
        "files",
    }
    if set(manifest) != manifest_keys:
        _fail("INVALID_MANIFEST", "manifest top-level fields differ")
    expected_manifest_bindings = {
        "schema_version": 1,
        "revision_id": str(revision.revision_id),
        "revision_hash": revision.revision_hash,
        "source_sha256": revision.source_sha256,
        "template_version": revision.template_version,
        "template_hash": revision.template_hash,
        "font_manifest_hash": revision.font_manifest_hash,
        "output_profile": revision.output_profile,
        "expected_row_ids": revision.expected_row_ids,
        "skipped_row_ids": revision.skipped_row_ids,
    }
    for key, expected in expected_manifest_bindings.items():
        if manifest.get(key) != expected:
            _fail("INVALID_MANIFEST", f"manifest {key} differs from revision")
    try:
        manifest_run_id = UUID(manifest.get("run_id"))
    except (TypeError, ValueError, AttributeError):
        _fail("INVALID_MANIFEST", "manifest run_id is not a UUID")

    name = manifest.get("package_name")
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 128
        or any(character in name for character in "/\\\r\n\0")
        or name in {".", ".."}
    ):
        _fail("PATH_ESCAPE", "package_name is unsafe")

    controlled = output_template(load_template(template_dir), revision.output_profile)
    planned = plan_pages(revision, controlled)
    if not planned.exportable:
        _fail("UNRESOLVED_REVISION", "revision cannot produce an exportable page plan")
    expected_page_mapping = [
        {
            "page_index": index,
            "row_id": page.row_id,
            "code": page.code,
            "relative_path": f"pdf/{page.code}.pdf",
        }
        for index, page in enumerate(planned.pages, start=1)
    ]
    if manifest.get("page_mapping") != expected_page_mapping:
        _fail("PAGE_BINDING_MISMATCH", "manifest page mapping differs")
    expected_formats = {
        "dxf": {"status": "provided", "artifacts": [f"{name}.dxf"]},
        "pdf": {
            "status": "provided",
            "artifacts": [
                *[f"pdf/{page.code}.pdf" for page in planned.pages],
                f"{name}.pdf",
            ],
        },
        "dwg": {"status": "disabled_not_provided", "artifacts": []},
    }
    if native:
        expected_formats["dwg"] = {"status": "provided", "artifacts": [f"{name}.dwg"]}
    if manifest.get("formats") != expected_formats:
        _fail("INVALID_MANIFEST", "manifest formats differ")
    render_reports = manifest.get("render_reports")
    if not isinstance(render_reports, list) or len(render_reports) != len(planned.pages):
        _fail("INVALID_MANIFEST", "manifest render reports do not cover every page")
    for index, (report, page) in enumerate(
        zip(render_reports, planned.pages, strict=True), start=1
    ):
        expected_trace = {
            "row_id": page.row_id,
            "code": page.code,
            "page_index": index,
        }
        if not isinstance(report, dict) or any(
            report.get(key) != value for key, value in expected_trace.items()
        ):
            _fail("PAGE_BINDING_MISMATCH", f"render report differs for {page.row_id}")
        transform = report.get("viewport_transform")
        if not isinstance(transform, dict) or transform.get("model_to_paper_scale") != (
            (SAMPLE_PRINT_SCALE if native else 1.0) / float(page.scale.denominator)
        ) or transform.get("origin_mm") != [
            float(page.placement.model_origin_mm.x),
            float(page.placement.model_origin_mm.y),
        ]:
            _fail("PAGE_BINDING_MISMATCH", f"render transform differs for {page.row_id}")
        if native:
            for required in (root / f"{name}.dwg", root / f"pdf/{page.code}.pdf"):
                if not required.is_file():
                    _fail("MISSING_ARTIFACT", f"missing artifact: {required.name}")
        if native and (
            report.get("renderer") != "opencadstudio"
            or report.get("plot_options") != plot_options(page, controlled)
            or report.get("source_dwg_sha256") != sha256_file(root / f"{name}.dwg")
            or report.get("pdf_sha256") != sha256_file(root / f"pdf/{page.code}.pdf")
            or report.get("print_policy") != "sample_fit_to_frame"
            or report.get("stroke_style", {}).get("physical_width_pt") != 0.72
            or report.get("stroke_style", {}).get("policy") != "engineer_sample_uniform_stroke_v1"
        ):
            _fail("PAGE_BINDING_MISMATCH", f"native plot binding differs for {page.row_id}")

    run_keys = {
        "schema_version",
        "run_id",
        "revision_id",
        "revision_hash",
        "state",
        "expected_row_ids",
        "manifest",
        "zip",
    }
    if set(run) != run_keys:
        _fail("INVALID_RUN_RECORD", "run record top-level fields differ")
    expected_run_bindings = {
        "schema_version": 1,
        "run_id": str(manifest_run_id),
        "revision_id": str(revision.revision_id),
        "revision_hash": revision.revision_hash,
        "state": "verified_candidate",
        "expected_row_ids": revision.expected_row_ids,
    }
    for key, expected in expected_run_bindings.items():
        if run.get(key) != expected:
            _fail("INVALID_RUN_RECORD", f"run record {key} differs")
    if set(run.get("manifest", {})) != {"relative_path", "sha256", "bytes"}:
        _fail("INVALID_RUN_RECORD", "run manifest binding fields differ")
    if set(run.get("zip", {})) != {"relative_path", "sha256", "bytes"}:
        _fail("INVALID_RUN_RECORD", "run ZIP binding fields differ")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        _fail("INVALID_MANIFEST", "manifest files must be non-empty")
    relative_paths = [item.get("relative_path") for item in files]
    if any(not isinstance(value, str) for value in relative_paths):
        _fail("INVALID_MANIFEST", "manifest relative paths must be strings")
    if len(relative_paths) != len(set(value.casefold() for value in relative_paths)):
        _fail("NAME_COLLISION", "manifest has duplicate or case-colliding paths")
    if "manifest.json" in relative_paths or any(item.get("kind") == "manifest" for item in files):
        _fail("INVALID_MANIFEST", "manifest must not hash itself")

    artifact_by_path: dict[str, Artifact] = {}
    for item in files:
        relative = item.get("relative_path")
        if isinstance(relative, str):
            _safe_path(root, relative)
        try:
            artifact = Artifact.model_validate(item)
        except Exception as exc:
            _fail("INVALID_MANIFEST", f"invalid artifact entry: {exc}")
        path = _safe_path(root, artifact.relative_path)
        if not path.is_file():
            _fail("MISSING_ARTIFACT", f"missing artifact: {artifact.relative_path}")
        if path.is_symlink():
            _fail("PATH_ESCAPE", f"artifact is a symbolic link: {artifact.relative_path}")
        if path.stat().st_size != artifact.bytes or sha256_file(path) != artifact.sha256:
            _fail("HASH_MISMATCH", f"artifact hash/size differs: {artifact.relative_path}")
        artifact_by_path[artifact.relative_path] = artifact

    code_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    row_by_id = {row.row_id: row for row in revision.rows}
    single_paths: list[Path] = []
    expected_pdf_paths: list[str] = []
    for index, row_id in enumerate(revision.expected_row_ids, start=1):
        code = row_by_id[row_id].values.code
        if not code_pattern.fullmatch(code):
            _fail("PATH_ESCAPE", f"unsafe code reached delivery boundary: {code!r}")
        relative = f"pdf/{code}.pdf"
        expected_pdf_paths.append(relative)
        path = root / relative
        _pdf(path, 1)
        single_paths.append(path)

    expected_artifacts = {
        f"{name}.dxf",
        f"{name}.pdf",
        "original.xlsx",
        "actual.xlsx",
        "row-report.json",
        *expected_pdf_paths,
    }
    if native:
        expected_artifacts.update({f"{name}.dwg", "cad-report.json", "revision.json"})
    if set(artifact_by_path) != expected_artifacts:
        missing = sorted(expected_artifacts - set(artifact_by_path))
        extra = sorted(set(artifact_by_path) - expected_artifacts)
        _fail("ARTIFACT_SET_MISMATCH", f"missing={missing}, extra={extra}")

    all_row_ids = [row.row_id for row in revision.rows]
    expected_specs: dict[str, tuple[ArtifactKind, str, list[str], int | None, int | None]] = {
        f"{name}.dxf": (
            ArtifactKind.DXF,
            "image/vnd.dxf",
            revision.expected_row_ids,
            None,
            None,
        ),
        f"{name}.pdf": (
            ArtifactKind.PDF_MERGED,
            "application/pdf",
            revision.expected_row_ids,
            len(single_paths),
            None,
        ),
        "original.xlsx": (
            ArtifactKind.EXCEL_ORIGINAL,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            all_row_ids,
            None,
            None,
        ),
        "actual.xlsx": (
            ArtifactKind.EXCEL_ACTUAL,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            revision.expected_row_ids,
            None,
            None,
        ),
        "row-report.json": (
            ArtifactKind.REPORT,
            "application/json",
            all_row_ids,
            None,
            None,
        ),
    }
    if native:
        expected_specs[f"{name}.dwg"] = (
            ArtifactKind.DWG, "image/vnd.dwg", revision.expected_row_ids, None, None,
        )
        expected_specs["cad-report.json"] = (
            ArtifactKind.REPORT, "application/json", revision.expected_row_ids, None, None,
        )
        expected_specs["revision.json"] = (
            ArtifactKind.REPORT, "application/json", all_row_ids, None, None,
        )
    for index, (row_id, relative) in enumerate(
        zip(revision.expected_row_ids, expected_pdf_paths, strict=True), start=1
    ):
        expected_specs[relative] = (
            ArtifactKind.PDF_SINGLE,
            "application/pdf",
            [row_id],
            1,
            index,
        )
    for relative, expected in expected_specs.items():
        artifact = artifact_by_path[relative]
        actual = (
            artifact.kind,
            artifact.media_type,
            artifact.row_ids,
            artifact.page_count,
            artifact.page_index,
        )
        if actual != expected:
            _fail("PAGE_BINDING_MISMATCH", f"artifact binding differs: {relative}")
        if artifact.run_id != manifest_run_id:
            _fail("INVALID_MANIFEST", f"artifact run_id differs: {relative}")
        if artifact.revision_hash != revision.revision_hash:
            _fail("REVISION_CONFLICT", f"artifact revision differs: {relative}")

    merged = root / f"{name}.pdf"
    _pdf(merged, len(single_paths))
    formal_dxf = root / f"{name}.dxf"
    try:
        inspect_dxf(
            formal_dxf,
            list(planned.pages),
            controlled["layout"],
            controlled["fonts"],
        )
    except Exception as exc:
        _fail("DXF_READBACK_FAILED", str(exc))

    _validate_workbooks(root, revision)
    _validate_report(root, revision)

    if native:
        if _load_json(root / "revision.json", "INVALID_REPORT") != revision.model_dump(mode="json"):
            _fail("REVISION_CONFLICT", "archived revision differs from the frozen revision")
        cad = _load_json(root / "cad-report.json", "INVALID_REPORT")
        if (cad.get("profile") != NATIVE_PROFILE
                or cad.get("adapter") != "opencadstudio"
                or cad.get("dwg_sha256") != sha256_file(root / f"{name}.dwg")
                or cad.get("input_dxf_sha256") != sha256_file(formal_dxf)
                or cad.get("render_reports") != render_reports
                or cad.get("readback", {}).get("passed") is not True):
            _fail("INVALID_REPORT", "native CAD report is not bound to the delivered files")
    else:
        font = prepare_runtime_font(controlled["fonts"], Path(__file__).resolve().parents[4])
    with tempfile.TemporaryDirectory(prefix="heater-delivery-reference-") as value:
        reference_root = Path(value)
        if native:
            try:
                verify_dwg_pdf(root / f"{name}.dwg", planned.pages, controlled, reference_root)
            except Exception as exc:
                _fail("DWG_READBACK_FAILED", str(exc))
        for index, (page, single) in enumerate(
            zip(planned.pages, single_paths, strict=True), start=1
        ):
            reference_pdf = reference_root / (f"{page.code}.pdf" if native else f"{index:03d}.pdf")
            reference_png = reference_root / f"{index:03d}.png"
            try:
                if not native:
                    render_page(
                        formal_dxf, reference_pdf, reference_png,
                        float(page.scale.denominator), font, controlled["fonts"],
                        model_origin_mm=(float(page.placement.model_origin_mm.x),
                                         float(page.placement.model_origin_mm.y)),
                    )
            except Exception as exc:
                _fail("PDF_REFERENCE_FAILED", f"cannot render {page.row_id}: {exc}")
            reference_pixels = _rendered_page_bytes(reference_pdf)
            if _rendered_page_bytes(single) != reference_pixels:
                _fail(
                    "PAGE_CONTENT_MISMATCH",
                    f"single PDF content differs from formal DXF for {page.row_id}",
                )
            if _rendered_page_bytes(merged, index - 1) != reference_pixels:
                _fail(
                    "PAGE_ORDER_MISMATCH",
                    f"merged PDF page {index} differs from formal DXF for {page.row_id}",
                )

    input_bindings = manifest.get("input_bindings")
    if not isinstance(input_bindings, dict) or set(input_bindings) != {
        "input_dxf_sha256",
        "formal_dxf_sha256",
        "pages_sha256",
        "original_workbook_sha256",
    }:
        _fail("INVALID_MANIFEST", "manifest input bindings differ")
    if input_bindings.get("formal_dxf_sha256") != sha256_file(formal_dxf):
        _fail("HASH_MISMATCH", "manifest formal DXF binding differs")
    if input_bindings.get("original_workbook_sha256") != revision.source_sha256:
        _fail("INPUT_HASH_MISMATCH", "manifest original workbook binding differs")
    for key in ("input_dxf_sha256", "pages_sha256"):
        value = input_bindings.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            _fail("INVALID_MANIFEST", f"manifest {key} is not a SHA-256")

    zip_relative = run.get("zip", {}).get("relative_path")
    if zip_relative != f"{name}.zip":
        _fail("INVALID_RUN_RECORD", "run record ZIP path differs")
    if run.get("manifest", {}).get("relative_path") != "manifest.json":
        _fail("INVALID_RUN_RECORD", "run record manifest path differs")
    zip_path = _safe_path(root, zip_relative)
    if (
        manifest_path.stat().st_size != run.get("manifest", {}).get("bytes")
        or sha256_file(manifest_path) != run.get("manifest", {}).get("sha256")
    ):
        _fail("HASH_MISMATCH", "outer run manifest hash differs")
    if (
        not zip_path.is_file()
        or zip_path.stat().st_size != run.get("zip", {}).get("bytes")
        or sha256_file(zip_path) != run.get("zip", {}).get("sha256")
    ):
        _fail("HASH_MISMATCH", "outer run ZIP hash differs")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            expected_names = sorted([*expected_artifacts, "manifest.json"])
            if sorted(names) != expected_names or len(names) != len(set(item.casefold() for item in names)):
                _fail("ARTIFACT_SET_MISMATCH", "ZIP collection differs from manifest candidate")
            for name_in_zip in names:
                _safe_path(root, name_in_zip)
                if archive.read(name_in_zip) != (root / name_in_zip).read_bytes():
                    _fail("HASH_MISMATCH", f"ZIP member differs: {name_in_zip}")
    except (OSError, zipfile.BadZipFile) as exc:
        _fail("INVALID_ZIP", str(exc))

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    allowed = {*expected_artifacts, "manifest.json", "run.json", f"{name}.zip"}
    if actual_files != allowed:
        _fail(
            "ARTIFACT_SET_MISMATCH",
            f"candidate directory has residual files: {sorted(actual_files - allowed)}",
        )
    return {
        "schema_version": 1,
        "status": "passed",
        "revision_hash": revision.revision_hash,
        "expected_row_ids": revision.expected_row_ids,
        "skipped_row_ids": revision.skipped_row_ids,
        "page_count": len(single_paths),
        "artifact_count": len(expected_artifacts),
        "manifest_sha256": sha256_file(manifest_path),
        "zip_sha256": sha256_file(zip_path),
    }
