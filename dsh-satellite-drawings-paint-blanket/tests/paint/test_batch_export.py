import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from thermal_drawings.drawing.export_pipeline import BatchExportError, export_batch


MODEL_REF = {"project_id": "p", "model_id": "m", "model_revision": 1, "assembly_digest": "a" * 64}


def paint(revision="r1", drawing=True, status="passed"):
    return {"revision_id": revision, "model_ref": MODEL_REF, "status": status,
            "drawing_document": {"id": "drawing"} if drawing else None}


def batch(*groups):
    return {"revision_id": "r1", "model_ref": MODEL_REF, "groups": list(groups)}


def verified_export(paint_result, output, config, *, preview=False):
    output.mkdir(parents=True, exist_ok=True)
    data = b"AC1032" + paint_result["drawing_document"]["id"].encode()
    (output / "drawing.dwg").write_bytes(data)
    return {
        "opencadstudio_save_verified": {"verified": True},
        "opencadstudio_reopen": {"passed": True},
        "opencadstudio_reverse_verified": {"verified": True},
        "readback": {"status": "pass"},
        "autocad_reopen": "not_run",
    }


def test_batch_export_packages_successes_and_manifest(tmp_path):
    value = batch(
        {"group_id": "front", "label": "Front", "paint_type": "white", "target_face_refs": [{"entity_id": "f1"}], "paint_result": paint()},
        {"group_id": "back", "label": "Back", "paint_type": "black", "target_face_refs": [{"entity_id": "f2"}], "paint_result": paint()},
    )
    evidence = export_batch(value, tmp_path, "unused.json", exporter=verified_export)
    manifest = json.loads((tmp_path / "paint-drawing-manifest.json").read_text())
    assert evidence["summary"] == {"total": 2, "succeeded": 2, "failed": 0}
    assert [item["status"] for item in manifest["groups"]] == ["succeeded", "succeeded"]
    with zipfile.ZipFile(tmp_path / "paint-drawings.zip") as archive:
        assert archive.namelist()[0] == "manifest.json"
        assert len(archive.namelist()) == 3
        assert json.loads(archive.read("manifest.json")) == manifest
        for item in manifest["groups"]:
            data = archive.read(item["dwg"]["path"])
            assert data[:6] == b"AC1032"
            assert hashlib.sha256(data).hexdigest() == item["dwg"]["sha256"]
            assert item["verification"]["readback_status"] == "pass"


def test_batch_export_continues_after_unavailable_and_conversion_failure(tmp_path):
    def exporter(paint_result, output, config, *, preview=False):
        if paint_result["drawing_document"]["id"] == "bad":
            output.mkdir(parents=True, exist_ok=True)
            (output / "partial.tmp").write_text("partial")
            raise RuntimeError("converter stopped")
        return verified_export(paint_result, output, config, preview=preview)

    good, bad = paint(), paint()
    good["drawing_document"]["id"] = "good"
    bad["drawing_document"]["id"] = "bad"
    value = batch(
        {"group_id": "no-drawing", "paint_result": paint(drawing=False, status="needs_review")},
        {"group_id": "bad-conversion", "paint_result": bad},
        {"group_id": "good", "paint_result": good},
    )
    export_batch(value, tmp_path, "unused.json", exporter=exporter)
    manifest = json.loads((tmp_path / "paint-drawing-manifest.json").read_text())
    assert manifest["summary"] == {"total": 3, "succeeded": 1, "failed": 2}
    assert manifest["groups"][0]["error"]["code"] == "result_unavailable"
    assert manifest["groups"][1]["error"] == {"code": "group_export_failed", "message": "converter stopped"}
    assert not any(path.name == "partial.tmp" for path in (tmp_path / "groups").rglob("*"))
    with zipfile.ZipFile(tmp_path / "paint-drawings.zip") as archive:
        assert len([name for name in archive.namelist() if name.endswith(".dwg")]) == 1


def test_batch_export_all_failures_raise_without_package(tmp_path):
    value = batch({"group_id": "failed", "status": "failed", "error": {"code": "topology", "message": "invalid"}})
    with pytest.raises(BatchExportError) as error:
        export_batch(value, tmp_path, "unused.json", exporter=verified_export)
    assert error.value.code == "batch_export_failed"
    assert not (tmp_path / "paint-drawings.zip").exists()


def test_batch_export_hashes_untrusted_group_ids_in_paths(tmp_path):
    value = batch({"group_id": "../not-a-path", "paint_result": paint()})
    export_batch(value, tmp_path, "unused.json", exporter=verified_export)
    paths = [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")]
    assert not any(".." in path for path in paths)
