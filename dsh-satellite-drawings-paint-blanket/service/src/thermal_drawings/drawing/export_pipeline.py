"""Real conversion of exact version-bound documents; always review drafts."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from .document import DrawingDocument
from .dxf_export import DrawingExporter
from .converter import DwgConverter
from ..domain.validation import canonical


def export_draft(paint, output, config, *, preview=False):
    document = DrawingDocument(paint['drawing_document'])
    DrawingExporter().write_dxf(document, output/'drawing.dxf')
    evidence = DwgConverter(json.loads(Path(config).read_text())['dwg'], inherit_worker_group=True).convert(output/'drawing.dxf', output/'drawing.dwg', document=document)
    evidence.update(revision_id=paint['revision_id'], draft=True, human_review='not_run', full_acceptance=False, result_status=paint['status'], acceptance_checks=paint.get('checks',[]))
    preview_status = {'status': 'not_requested', 'revision_id': paint['revision_id']}
    if preview:
        converter_config = json.loads(Path(config).read_text())['dwg']
        if converter_config.get('adapter') == 'opencadstudio':
            from .opencad_preview import render_export_preview
            preview_status = render_export_preview(output/'drawing.dwg', output/'drawing-preview.png',
                                                   config, paint['revision_id'])
        else:
            preview_status = {'status': 'unavailable', 'reason': 'Configured converter has no application preview',
                              'revision_id': paint['revision_id'],
                              'source_dwg_sha256': evidence['output']['sha256']}
        (output/'preview-status.json').write_text(canonical(preview_status))
    evidence['preview'] = preview_status
    (output/'conversion.json').write_text(canonical(evidence))
    return evidence


class BatchExportError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _file(path):
    path = Path(path)
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def _zip_entry(archive, name, data):
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def _verification(evidence):
    return {
        "save_verified": bool(evidence.get("opencadstudio_save_verified", {}).get("verified")),
        "reopen_verified": evidence.get("opencadstudio_reopen", {}).get("passed") is True,
        "reverse_verified": bool(evidence.get("opencadstudio_reverse_verified", {}).get("verified")),
        "readback_status": evidence.get("readback", {}).get("status"),
        "autocad_reopen": evidence.get("autocad_reopen", "not_run"),
    }


def export_batch(batch, output, config, *, preview=False, exporter=None):
    """Serially export available batch groups and package verified DWGs.

    A failed group is removed from the output tree and recorded in the manifest.
    At least one verified DWG is required before a package is published.
    """
    if not isinstance(batch, dict) or not isinstance(batch.get("groups"), list) or not batch["groups"]:
        raise BatchExportError("invalid_batch", "A non-empty paint batch result is required")
    revision_id, model_ref = batch.get("revision_id"), batch.get("model_ref")
    if not isinstance(revision_id, str) or not revision_id or not isinstance(model_ref, dict):
        raise BatchExportError("invalid_batch", "Batch revision and model reference are required")
    exporter = exporter or export_draft
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    groups_root = output / "groups"
    groups_root.mkdir(exist_ok=False)
    manifest_groups, package_files, seen = [], [], set()
    for index, group in enumerate(batch["groups"], 1):
        group_id = group.get("group_id") if isinstance(group, dict) else None
        if not isinstance(group_id, str) or not group_id or group_id in seen:
            raise BatchExportError("invalid_group_id", "Batch group IDs must be unique")
        seen.add(group_id)
        safe_id = hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:16]
        stem = f"{index:03d}-{safe_id}"
        entry = {key: group[key] for key in (
            "group_id", "label", "component_name", "instance_id", "instance_name", "direction",
            "direction_label", "normal", "side", "side_label", "paint_type", "target_face_refs",
        ) if key in group}
        entry.update(status="failed", revision_id=revision_id, model_ref=model_ref)
        paint = group.get("paint", group.get("paint_result"))
        if not isinstance(paint, dict) or paint.get("drawing_document") is None or paint.get("status") == "failed":
            entry["error"] = group.get("error") or {
                "code": "result_unavailable", "message": "Surface group has no exportable drawing",
            }
            manifest_groups.append(entry)
            continue
        if paint.get("revision_id") != revision_id or paint.get("model_ref") != model_ref:
            entry["error"] = {"code": "result_conflict", "message": "Surface result is not bound to this batch"}
            manifest_groups.append(entry)
            continue
        directory = groups_root / stem
        directory.mkdir()
        try:
            evidence = exporter(paint, directory, config, preview=preview)
            dwg = directory / "drawing.dwg"
            if not dwg.is_file() or dwg.read_bytes()[:6] != b"AC1032":
                raise BatchExportError("invalid_dwg", "Verified DWG 2018 output is missing")
            record = _file(dwg)
            package_name = stem + ".dwg"
            entry.update(status="succeeded", dwg={"path": package_name, **record}, verification=_verification(evidence))
            package_files.append((package_name, dwg.read_bytes()))
        except Exception as exc:
            shutil.rmtree(directory, ignore_errors=True)
            entry["error"] = {
                "code": getattr(exc, "code", "group_export_failed"),
                "message": str(exc)[:500] or type(exc).__name__,
            }
        manifest_groups.append(entry)
    succeeded = sum(group["status"] == "succeeded" for group in manifest_groups)
    failed = len(manifest_groups) - succeeded
    if not succeeded:
        raise BatchExportError("batch_export_failed", "No surface group produced a verified DWG")
    manifest = {
        "schema_version": 1,
        "kind": "paint_drawing_batch",
        "revision_id": revision_id,
        "model_ref": model_ref,
        "draft": True,
        "human_review": "not_run",
        "status": "needs_review",
        "summary": {"total": len(manifest_groups), "succeeded": succeeded, "failed": failed},
        "groups": manifest_groups,
    }
    manifest_bytes = canonical(manifest).encode("utf-8")
    (output / "paint-drawing-manifest.json").write_bytes(manifest_bytes)
    package = output / "paint-drawings.zip"
    with zipfile.ZipFile(package, "x") as archive:
        _zip_entry(archive, "manifest.json", manifest_bytes)
        for name, data in package_files:
            _zip_entry(archive, name, data)
    evidence = {
        "status": "needs_review",
        "kind": "paint_drawing_batch",
        "revision_id": revision_id,
        "draft": True,
        "human_review": "not_run",
        "full_acceptance": False,
        "summary": manifest["summary"],
        "manifest": _file(output / "paint-drawing-manifest.json"),
        "package": _file(package),
        "autocad_reopen": "not_run",
    }
    (output / "conversion.json").write_text(canonical(evidence))
    return evidence
