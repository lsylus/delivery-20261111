"""Batch orchestration over immutable single-surface PaintResult values."""
import copy
from pathlib import Path
import re

from ..domain.validation import canonical, validate
from .pipeline import generate


GROUP_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
METADATA_FIELDS = (
    "label", "component_name", "direction", "normal", "side", "paint_type",
    "opposite_group_id",
)


class PaintBatchError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _validated_groups(groups, model_ref):
    if not isinstance(groups, list) or not 1 <= len(groups) <= 128:
        raise PaintBatchError("invalid_batch", "Paint batch requires 1..128 surface groups")
    seen = set()
    values = []
    for item in groups:
        if not isinstance(item, dict) or set(item) - ({"group_id", "parameters"} | set(METADATA_FIELDS)):
            raise PaintBatchError("invalid_group", "Surface group has unsupported fields")
        group_id = item.get("group_id")
        if not isinstance(group_id, str) or not GROUP_ID.fullmatch(group_id) or group_id in seen:
            raise PaintBatchError("invalid_group_id", "Surface group IDs must be unique safe identifiers")
        parameters = item.get("parameters")
        if not isinstance(parameters, dict) or parameters.get("model_ref") != model_ref:
            raise PaintBatchError("model_conflict", "Every surface group must use the loaded model reference")
        refs = parameters.get("target_face_refs")
        if not isinstance(refs, list) or not refs:
            raise PaintBatchError("empty_group", "Every surface group requires target face references")
        seen.add(group_id)
        values.append(copy.deepcopy(item))
    return values


def _generate_legacy_batch(groups, model, revision_id, *, output=None, generator=None):
    """Generate independent atomic results without allowing one group to abort the batch."""
    if not isinstance(revision_id, str) or not revision_id:
        raise PaintBatchError("invalid_revision", "A version-bound revision ID is required")
    items = _validated_groups(groups, model.model_ref)
    generator = generator or generate
    output = Path(output) if output is not None else None
    results = []
    counts = {"total": len(items), "passed": 0, "needs_review": 0, "failed": 0, "exportable": 0}
    for item in items:
        group_id = item["group_id"]
        group_output = output / "groups" / group_id if output is not None else None
        if group_output is not None:
            group_output.mkdir(parents=True, exist_ok=False)
        entry = {key: copy.deepcopy(item[key]) for key in ("group_id", *METADATA_FIELDS) if key in item}
        entry["target_face_refs"] = copy.deepcopy(item["parameters"]["target_face_refs"])
        try:
            paint = generator(item["parameters"], model, revision_id, output=group_output)
            if not isinstance(paint, dict) or paint.get("revision_id") != revision_id or paint.get("model_ref") != model.model_ref:
                raise PaintBatchError("result_conflict", "Atomic paint result is not bound to this batch")
            status = paint.get("status")
            if status not in ("passed", "needs_review", "failed"):
                raise PaintBatchError("invalid_result", "Atomic paint result has an invalid status")
            entry.update(status=status, paint_result=paint)
            counts[status] += 1
            if paint.get("drawing_document") is not None and status != "failed":
                counts["exportable"] += 1
        except Exception as exc:
            entry.update(status="failed", error={
                "code": getattr(exc, "code", "group_generation_failed"),
                "message": str(exc)[:500] or type(exc).__name__,
            })
            counts["failed"] += 1
        results.append(entry)
    status = "passed" if counts["passed"] == counts["exportable"] == counts["total"] else "needs_review" if counts["exportable"] else "failed"
    return {
        "schema_version": 1,
        "revision_id": revision_id,
        "model_ref": copy.deepcopy(model.model_ref),
        "status": status,
        "groups": results,
        "summary": counts,
    }


def _annotate(paint, group):
    document = paint.get("drawing_document")
    if document is None:
        return
    document = copy.deepcopy(document)
    if not any(layer["name"] == "TEXT" for layer in document["layers"]):
        document["layers"].append({"name": "TEXT", "color": 3, "line_type": "CONTINUOUS"})
    points = [point for entity in document["entities"] if entity["kind"] == "polyline" for point in entity["points"]]
    x = min((point[0] for point in points), default=0)
    y = max((point[1] for point in points), default=0) + 5
    labels = [
        f"{group['instance_name']} | {group['direction_label']} | {group['side_label']}",
        f"Paint: {group['paint_type']}",
        "ANSI31 hatch: protected area",
    ]
    for index, text in enumerate(labels, 1):
        document["entities"].append({
            "id": f"batch-note-{group['group_id']}-{index}", "kind": "text", "layer": "TEXT",
            "source_refs": group["target_face_refs"], "text": text,
            "position": [x, y + (index - 1) * 4], "height_mm": 2.5,
        })
    paint["drawing_document"] = document


def _generate_contract_batch(params, model, revision_id, *, output=None, generator=None):
    validate("paint", params, "PaintBatchInput")
    groups = params["target_face_groups"]
    flattened = [ref for group in groups for ref in group["target_face_refs"]]
    if len(flattened) != len({canonical(ref) for ref in flattened}) or flattened != params["target_face_refs"]:
        raise PaintBatchError("invalid_batch", "target_face_groups must partition target_face_refs in stable order")
    generator = generator or generate
    base = {key: copy.deepcopy(value) for key, value in params.items() if key != "target_face_groups"}
    results = []
    counts = {"total": len(groups), "passed": 0, "needs_review": 0, "failed": 0, "exportable": 0}
    for group in groups:
        single = dict(base, target_face_refs=group["target_face_refs"])
        entry = copy.deepcopy(group)
        try:
            paint = generator(single, model, revision_id, output=output)
            _annotate(paint, group)
            status = paint["status"]
            counts[status] += 1
            if paint.get("drawing_document") is not None and status != "failed":
                counts["exportable"] += 1
            message = None
            if status == "failed":
                observed = paint["diagnostics"][0]["observed"] if paint["diagnostics"] else {}
                message = observed.get("message", "Paint group failed")
            entry.update(status=status, paint=paint,
                         error={"code": "paint_group_failed", "message": message} if message else None)
        except Exception as exc:
            counts["failed"] += 1
            entry.update(status="failed", paint=None,
                         error={"code": getattr(exc, "code", "group_generation_failed"), "message": str(exc)[:500]})
        results.append(entry)
    status = "failed" if counts["failed"] == len(results) else "needs_review" if counts["failed"] or counts["needs_review"] else "passed"
    check_status = "fail" if status == "failed" else "needs_review" if status == "needs_review" else "pass"
    result = {
        "schema_version": 1, "revision_id": revision_id, "model_ref": copy.deepcopy(model.model_ref),
        "status": status, "groups": results, "summary": counts,
        "checks": [{
            "id": "paint_batch", "status": check_status, "scope_refs": params["target_face_refs"],
            "observed": counts, "limit": None, "units": None, "algorithm_version": "paint-batch-v1",
            "evidence_refs": [], "reason": "Every selected planar group was processed independently.",
        }],
    }
    validate("paint", result, "PaintBatchResult")
    return result


def generate_batch(groups, model, revision_id, *, output=None, generator=None):
    """Accept the public batch input while retaining the isolated helper API."""
    if isinstance(groups, dict):
        return _generate_contract_batch(groups, model, revision_id, output=output, generator=generator)
    return _generate_legacy_batch(groups, model, revision_id, output=output, generator=generator)
