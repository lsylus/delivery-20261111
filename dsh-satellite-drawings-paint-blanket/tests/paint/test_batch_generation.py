from pathlib import Path

import pytest

from thermal_drawings.paint.batch import PaintBatchError, generate_batch


MODEL_REF = {"project_id": "p", "model_id": "m", "model_revision": 1, "assembly_digest": "a" * 64}


class Model:
    model_ref = MODEL_REF


def parameters(group_id):
    return {"model_ref": MODEL_REF, "target_face_refs": [{"entity_id": group_id}]}


def atomic(revision, status="passed", drawing=True):
    return {
        "revision_id": revision,
        "model_ref": MODEL_REF,
        "status": status,
        "drawing_document": {"id": "drawing"} if drawing else None,
    }


def test_batch_keeps_atomic_results_and_isolates_group_failure(tmp_path):
    calls = []

    def generator(params, model, revision, *, output):
        calls.append((params["target_face_refs"][0]["entity_id"], output))
        if len(calls) == 2:
            raise RuntimeError("bad topology")
        return atomic(revision)

    groups = [
        {"group_id": "front", "label": "Front", "parameters": parameters("front")},
        {"group_id": "back", "label": "Back", "parameters": parameters("back")},
    ]
    result = generate_batch(groups, Model(), "r1", output=tmp_path, generator=generator)
    assert result["status"] == "needs_review"
    assert result["summary"] == {"total": 2, "passed": 1, "needs_review": 0, "failed": 1, "exportable": 1}
    assert result["groups"][0]["paint_result"]["drawing_document"] == {"id": "drawing"}
    assert result["groups"][1]["error"] == {"code": "group_generation_failed", "message": "bad topology"}
    assert calls == [("front", tmp_path / "groups" / "front"), ("back", tmp_path / "groups" / "back")]


def test_batch_with_only_non_exportable_results_is_failed():
    result = generate_batch(
        [{"group_id": "front", "parameters": parameters("front")}], Model(), "r1",
        generator=lambda params, model, revision, output: atomic(revision, "needs_review", drawing=False),
    )
    assert result["status"] == "failed"
    assert result["summary"]["exportable"] == 0
    assert result["groups"][0]["status"] == "needs_review"


@pytest.mark.parametrize("groups,code", [
    ([], "invalid_batch"),
    ([{"group_id": "../escape", "parameters": parameters("x")}], "invalid_group_id"),
    ([{"group_id": "same", "parameters": parameters("a")}, {"group_id": "same", "parameters": parameters("b")}], "invalid_group_id"),
    ([{"group_id": "x", "parameters": {"model_ref": {}}}], "model_conflict"),
])
def test_batch_rejects_unbounded_ambiguous_or_unsafe_groups(groups, code):
    with pytest.raises(PaintBatchError) as error:
        generate_batch(groups, Model(), "r1", generator=lambda *args, **kwargs: None)
    assert error.value.code == code
