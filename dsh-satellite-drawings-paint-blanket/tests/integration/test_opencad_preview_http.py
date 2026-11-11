"""Public OperationEnvelope + real HTTP/worker/OpenCADStudio preview acceptance."""
import hashlib
import json
import os
from pathlib import Path
import sys
import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from contracts import validate as validate_public
from thermal_drawings.domain.validation import validate as validate_packaged
from thermal_drawings.domain.errors import ServiceError


@pytest.mark.parametrize("module", ["paint", "blanket"])
@pytest.mark.parametrize("preview", [None, False, True])
def test_operation_contract_accepts_optional_boolean_preview(module, preview):
    value = json.loads((ROOT / "fixtures/contracts/operation-export-preview.json").read_text())
    value["module"] = module
    if preview is None:
        value["parameters"].pop("preview")
    else:
        value["parameters"]["preview"] = preview
    validate_public("operation", value, "OperationEnvelope")
    validate_packaged("operation", value, "OperationEnvelope")
    assert (ROOT / "contracts/operation.schema.json").read_bytes() == (
        ROOT / "service/src/thermal_drawings/domain/schemas/operation.schema.json").read_bytes()


@pytest.mark.parametrize("change", [{"preview": 1}, {"preview": "true"}, {"preview": None},
                                   {"preview": True, "path": "/tmp/not-allowed"}])
def test_operation_contract_rejects_invalid_preview_and_output_paths(change):
    value = json.loads((ROOT / "fixtures/contracts/operation-export-preview.json").read_text())
    value["parameters"].update(change)
    with pytest.raises(ValidationError):
        validate_public("operation", value, "OperationEnvelope")
    # Packaged schema uses the service's typed error envelope.
    with pytest.raises(ServiceError):
        validate_packaged("operation", value, "OperationEnvelope")


@pytest.mark.skipif(not os.environ.get("THERMAL_OPENCADSTUDIO"), reason="Real OpenCADStudio required")
def test_http_submit_to_published_real_dwg_preview(tmp_path):
    from b09_workflow import generate_case, completed, head, result
    from http_case import Service, download
    service = Service(tmp_path / "http-preview", timeout=180, upload_limit=64*1024*1024)
    try:
        service.stop()
        config = json.loads(service.config.read_text())
        converter_path = tmp_path / "converter.json"
        converter_path.write_text(json.dumps({"dwg": {
            "adapter": "opencadstudio", "executable": os.environ["THERMAL_OPENCADSTUDIO"],
            "target_version": "ACAD2018", "timeout_s": 30, "license_ref": None,
            "font_paths": ["/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"]}}))
        config.update(converter_config=str(converter_path), memory_limit_mb=32768)
        service.config.write_text(json.dumps(config))
        service.start()
        project, revision, generated = generate_case(service)
        completed(service, project, revision, "drawing.edit_annotation", {
            "result_id": generated["id"], "annotation_id": "preview-note",
            "text": "真实预览与DWG同版本", "position": [-45, -37]})
        revision = head(service, project)
        source = result(service, project)
        # Exercise the public JSON schema and HTTP route, not only Python validators.
        service.operation(project, revision, "drawing.export",
                          {"result_id": source["result_id"], "draft": True, "preview": 1},
                          expected=422)
        response = service.operation(project, revision, "drawing.export",
                                     {"result_id": source["result_id"], "draft": True, "preview": True})
        exported = service.wait(response["run_id"])
        assert exported["state"] == "succeeded", exported
        files = download(service, exported)
        assert files["drawing.dwg"][:6] == b"AC1032"
        assert files["drawing-preview.png"][:8] == b"\x89PNG\r\n\x1a\n"
        png = next(a for a in exported["artifacts"] if a["role"] == "drawing_preview")
        assert png["format"] == "PNG" and png["mime_type"] == "image/png"
        assert png["run_id"] == exported["id"] and png["revision_id"] == revision["id"]
        dwg_hash = hashlib.sha256(files["drawing.dwg"]).hexdigest()
        binding = next(check for check in png["validation"] if check["id"] == "dwg-preview-binding")
        assert binding["observed"] == {"source_dwg_sha256": dwg_hash, "revision_id": revision["id"]}
        status = json.loads(files["preview-status.json"])
        report = json.loads(files["drawing-preview.preview.json"])
        assert status["status"] == "ready" and status["source_dwg_sha256"] == dwg_hash
        assert report["input"]["sha256"] == dwg_hash and report["revision_id"] == revision["id"]
        assert report["text_records"]["count"] >= 1 and report["missing_fonts"] == []
        assert head(service, project) == revision
        service.call("GET", png["download_url"].removeprefix("/api/v1"), who="bob", expected=404)
    finally:
        service.close()
