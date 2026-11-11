"""Specific interoperability checks; no fake successful DWG capability."""
import json
import os
from pathlib import Path
import sys
import ezdxf
import pytest
from thermal_drawings.drawing.converter import ConversionError, DwgConverter
from thermal_drawings.drawing.document import DrawingDocument
from thermal_drawings.drawing.dxf_export import DrawingExporter
from thermal_drawings.drawing.opencadstudio import OpenCadStudioConverter, validate_opencad_readback
from thermal_drawings.drawing.validation import validate_dxf

ROOT = Path(__file__).resolve().parents[2]


def fixture_dxf(tmp_path):
    document = DrawingDocument.read(ROOT / "fixtures/synthetic/drawing_sample.json")
    path = DrawingExporter().write_dxf(document, tmp_path / "input.dxf")
    return document, path


def add_orphan_style(path):
    text = path.read_text()
    objects = text.index("  2\nOBJECTS\n")
    end = text.index("  0\nENDSEC", objects)
    tags = "  0\nTABLESTYLE\n  5\nFFFFFF\n330\n0\n100\nAcDbTableStyle\n  3\nTest\n"
    path.write_text(text[:end] + tags + text[end:])


def test_installed_wrapper_is_rejected_for_profile_isolation(tmp_path):
    wrapper = tmp_path / "OpenCADStudio"
    wrapper.write_text("#!/bin/sh\nexit 0\n")
    wrapper.chmod(0o700)
    caps = DwgConverter({"adapter": "opencadstudio", "executable": str(wrapper)}).capabilities()
    assert caps["status"] == "blocked"
    assert caps["reasons"] == ["native_binary_required_for_profile_isolation"]


def test_known_orphan_normalization_keeps_raw_bytes_and_all_geometry(tmp_path):
    document, raw = fixture_dxf(tmp_path)
    add_orphan_style(raw)
    original = raw.read_bytes()
    with pytest.raises(ValueError, match="audit"):
        validate_dxf(document, raw)
    normalized = tmp_path / "normalized.dxf"
    result = validate_opencad_readback(document, raw, normalized)
    assert result["status"] == "pass"
    assert result["raw_audit_fixes"] == 1
    assert result["dwg_modified"] is False
    assert raw.read_bytes() == original
    assert result["entity_counts"]["DIMENSION"] == 2
    assert validate_dxf(document, normalized)["entity_count"] == len(document.to_dict()["entities"])


def test_known_orphan_exception_cannot_hide_geometry_change(tmp_path):
    document, raw = fixture_dxf(tmp_path)
    add_orphan_style(raw)
    doc = ezdxf.readfile(raw)
    next(iter(doc.modelspace().query("CIRCLE"))).dxf.radius += 1
    doc.saveas(raw)
    with pytest.raises(ValueError, match="numeric mismatch"):
        validate_opencad_readback(document, raw, tmp_path / "normalized.dxf")


def test_unrelated_audit_repair_is_rejected(tmp_path):
    document, raw = fixture_dxf(tmp_path)
    doc = ezdxf.readfile(raw)
    item = next(iter(doc.modelspace().query("CIRCLE")))
    item.dxf.linetype = "MISSING_LINETYPE"
    doc.saveas(raw)
    with pytest.raises(ConversionError, match="Unexpected DXF repair"):
        validate_opencad_readback(document, raw, tmp_path / "normalized.dxf")


def test_existing_delivery_is_preserved(tmp_path):
    document, raw = fixture_dxf(tmp_path)
    destination = tmp_path / "prior.dwg"
    destination.write_bytes(b"prior-delivery")
    config = dict(adapter="opencadstudio", executable=sys.executable,
                  target_version="ACAD2018", timeout_s=5, font_paths=[str(tmp_path / "DroidSansFallbackFull.ttf")])
    Path(config["font_paths"][0]).write_bytes(b"configuration-only-font")
    with pytest.raises(ConversionError) as error:
        DwgConverter(config).convert(raw, destination, document=document)
    assert error.value.code == "destination_exists"
    assert destination.read_bytes() == b"prior-delivery"


@pytest.mark.skipif(not os.environ.get("THERMAL_OPENCADSTUDIO"), reason="Real installed OpenCADStudio required")
def test_real_opencadstudio_dwg_reopen_unicode_and_geometry(tmp_path):
    document, dxf = fixture_dxf(tmp_path)
    config = dict(adapter="opencadstudio", executable=os.environ.get("THERMAL_OPENCADSTUDIO"),
                  target_version="ACAD2018", timeout_s=30,
                  font_paths=["/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"])
    result = DwgConverter(config).convert(dxf, tmp_path / "drawing.dwg", document=document)
    assert result["opencadstudio_save_verified"]["verified"] is True
    assert result["opencadstudio_reverse_verified"]["verified"] is True
    assert result["opencadstudio_reopen"] == {"passed": True, "missing_fonts": []}
    assert result["readback"]["status"] == "pass"
    assert result["readback"]["entity_counts"]["DIMENSION"] == 2
    assert (tmp_path / "drawing.dwg").read_bytes()[:6] == b"AC1032"
    assert result["capability"]["real_conversion_verified"]
    assert not list(tmp_path.glob(".opencad-*"))

@pytest.mark.parametrize("preview", [True, False])
def test_export_preview_parameter_is_explicit_boolean(preview):
    from thermal_drawings.paint.commands import validate_command
    validate_command("drawing.export", {"result_id": "result", "draft": True, "preview": preview})


@pytest.mark.parametrize("preview", ["true", 1, None, {"path": "/tmp/escape"}])
def test_export_preview_rejects_non_boolean_and_output_paths(preview):
    from thermal_drawings.paint.commands import validate_command
    from thermal_drawings.domain.errors import ServiceError
    with pytest.raises(ServiceError):
        validate_command("drawing.export", {"result_id": "result", "draft": True, "preview": preview})


@pytest.mark.skipif(not os.environ.get("THERMAL_OPENCADSTUDIO"), reason="Real installed OpenCADStudio required")
def test_real_export_adds_bound_preview_and_preview_failure_preserves_dwg(tmp_path):
    from thermal_drawings.drawing.export_pipeline import export_draft
    from thermal_drawings.drawing.opencad_preview import render_export_preview
    from thermal_drawings.drawing.validation import file_record
    config = {"dwg": dict(adapter="opencadstudio", executable=os.environ["THERMAL_OPENCADSTUDIO"],
                         target_version="ACAD2018", timeout_s=30,
                         font_paths=["/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"])}
    path = tmp_path / "converter.json"
    path.write_text(json.dumps(config))
    drawing = json.loads((ROOT / "fixtures/synthetic/drawing_sample.json").read_text())
    output = tmp_path / "export"
    output.mkdir()
    result = export_draft(dict(drawing_document=drawing, revision_id=drawing["revision_id"],
                               status="needs_review"), output, path, preview=True)
    assert result["preview"]["status"] == "ready"
    report = json.loads((output / "drawing-preview.preview.json").read_text())
    before = (output / "drawing.dwg").read_bytes()
    assert report["revision_id"] == drawing["revision_id"]
    assert report["input"]["sha256"] == file_record(output / "drawing.dwg")["sha256"]
    assert (output / "drawing-preview.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert report["text_records"]["count"] >= 1
    # A missing application affects only the optional preview, never the real DWG.
    config["dwg"]["executable"] = str(tmp_path / "missing-application")
    path.write_text(json.dumps(config))
    failed = render_export_preview(output / "drawing.dwg", output / "unavailable.png",
                                   path, drawing["revision_id"])
    assert failed["status"] == "unavailable"
    assert (output / "drawing.dwg").read_bytes() == before
    assert not (output / "unavailable.png").exists()


def test_preview_cleanup_waits_for_stubborn_owned_child(tmp_path):
    import subprocess
    import time
    from thermal_drawings.drawing.opencad_preview import terminate_processes
    ready = tmp_path / "ready"
    late_write = tmp_path / "late-profile-write"
    code = ("import pathlib,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            "pathlib.Path(" + repr(str(ready)) + ").touch(); time.sleep(2); "
            "pathlib.Path(" + repr(str(late_write)) + ").touch()")
    child = subprocess.Popen([sys.executable, "-c", code])
    try:
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        terminate_processes([child.pid], timeout=0.1)
        assert child.wait(timeout=1) != 0
        assert not late_write.exists()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=1)
