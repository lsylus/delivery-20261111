from __future__ import annotations

import copy
import importlib.util
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

import ezdxf
import pytest

from heater_drawing.domain.models import DrawingPage, validate_contract_semantics
from heater_drawing.drawing import dwg_adapter, fonts
from heater_drawing.drawing.dwg_adapter import ConversionError
from heater_drawing.drawing.display_profile import (
    controlled_dimension_linetype_signature,
    controlled_layer_error,
    controlled_layer_signature,
)
from heater_drawing.drawing.dxf_writer import expected_text_records, write_page_dxf
from heater_drawing.drawing.pdf_renderer import RenderError, render_page
from heater_drawing.drawing.readback import ReadbackError, inspect_dxf
from heater_drawing.drawing.sample import load_sample
from heater_drawing.drawing.template import TemplateError, load_template

ROOT = Path(__file__).resolve().parents[2]


def test_missing_dwg_tool_is_not_configured() -> None:
    result = dwg_adapter.capabilities(None, None)
    assert result.state == "not_configured"
    assert result.license_scope == "none_for_this_project"


def test_authorization_metadata_without_roundtrip_is_unverified(tmp_path: Path) -> None:
    record = tmp_path / "license.json"
    record.write_text(json.dumps({"project": "heater-drawing", "evaluation_authorized": True}), encoding="utf-8")
    result = dwg_adapter.capabilities(Path(sys.executable), record)
    assert result.state == "available_unverified"
    assert "identify the converter" in result.detail


def test_fake_roundtrip_with_arbitrary_python_remains_unverified(tmp_path: Path) -> None:
    input_path = tmp_path / "input.dxf"
    dwg_path = tmp_path / "output.dwg"
    roundtrip_path = tmp_path / "roundtrip.dxf"
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    input_path.write_text("not a DXF", encoding="utf-8")
    dwg_path.write_bytes(b"AC1032" + b"x" * 2048)
    roundtrip_path.write_text("not a DXF either", encoding="utf-8")
    stdout_path.write_text("fake forward and reverse", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")

    def artifact(path: Path) -> dict:
        return {"path": str(path.resolve()), "sha256": dwg_adapter._sha256(path)}

    converter = Path(sys.executable).resolve()
    items = {"input": artifact(input_path), "dwg": artifact(dwg_path), "roundtrip_dxf": artifact(roundtrip_path)}
    command = lambda source, output: {
        "argv": [str(converter), "fake"], "exit_code": 0,
        "input_path": items[source]["path"], "input_sha256": items[source]["sha256"],
        "output_path": items[output]["path"], "output_sha256": items[output]["sha256"],
        "stdout": artifact(stdout_path), "stderr": artifact(stderr_path),
    }
    record = tmp_path / "license.json"
    record.write_text(json.dumps({
        "project": "heater-drawing", "evaluation_authorized": True,
        "converter": {"product": "ODA File Converter", "version": "fake", "path": str(converter), "sha256": dwg_adapter._sha256(converter)},
        "round_trip_evidence": {**items, "commands": {"forward": command("input", "dwg"), "reverse": command("dwg", "roundtrip_dxf")}},
    }), encoding="utf-8")
    result = dwg_adapter.capabilities(converter, record)
    assert result.state == "available_unverified"
    assert "not ODAFileConverter" in result.detail


def test_renamed_python_lacks_trusted_oda_identity(tmp_path: Path) -> None:
    name = "ODAFileConverter.exe" if sys.platform == "win32" else "ODAFileConverter"
    converter = tmp_path / name
    shutil.copyfile(sys.executable, converter)
    error = dwg_adapter._trusted_executable_error(converter)
    assert error is not None
    assert "Open Design Alliance" in error or "code-trusted vendor" in error


def test_capability_rejects_low_entropy_dwg_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    converter = tmp_path / ("ODAFileConverter.exe" if sys.platform == "win32" else "ODAFileConverter")
    shutil.copyfile(sys.executable, converter)
    input_path = tmp_path / "input.dxf"
    roundtrip_path = tmp_path / "roundtrip.dxf"
    for path in (input_path, roundtrip_path):
        document = ezdxf.new("R2018")
        document.header["$INSUNITS"] = 4
        document.modelspace().add_line((0, 0), (1, 1))
        document.saveas(path)
    dwg_path = tmp_path / "output.dwg"
    dwg_path.write_bytes(b"AC1032" + b"x" * 2048)

    def artifact(path: Path) -> dict:
        return {"path": str(path.resolve()), "sha256": dwg_adapter._sha256(path)}

    monkeypatch.setattr(dwg_adapter, "_validate_converter_identity", lambda *_args: None)
    record = tmp_path / "license.json"
    record.write_text(json.dumps({
        "project": "heater-drawing",
        "evaluation_authorized": True,
        "operator": {"id": "test-only", "name": "Test Only"},
        "performed_at": datetime.now(timezone.utc).isoformat(),
        "converter": {
            "product": "ODA File Converter", "version": "test-only",
            "path": str(converter.resolve()), "sha256": dwg_adapter._sha256(converter),
        },
        "round_trip_evidence": {
            "input": artifact(input_path), "dwg": artifact(dwg_path),
            "roundtrip_dxf": artifact(roundtrip_path), "commands": {},
        },
    }), encoding="utf-8")
    result = dwg_adapter.capabilities(converter, record)
    assert result.state == "available_unverified"
    assert "low entropy" in result.detail


def test_command_claim_without_helper_record_is_unverified(tmp_path: Path) -> None:
    converter = Path(sys.executable).resolve()
    source = tmp_path / "input.dxf"
    output = tmp_path / "output.dwg"
    source.write_bytes(b"input")
    output.write_bytes(b"output")
    error = dwg_adapter._command_evidence(
        {}, converter,
        (source.resolve(), dwg_adapter._sha256(source)),
        (output.resolve(), dwg_adapter._sha256(output)),
        "forward",
    )
    assert error == "forward command lacks a controlled execution record"


def test_missing_converter_fails(tmp_path: Path) -> None:
    with pytest.raises(ConversionError, match="missing"):
        dwg_adapter.run_fixed_command(tmp_path / "missing", [], tmp_path / "out.dwg", 1)


def test_converter_timeout_kills_process_group(tmp_path: Path) -> None:
    with pytest.raises(ConversionError, match="timed out") as caught:
        dwg_adapter.run_fixed_command(Path(sys.executable), ["-c", "import time; time.sleep(5)"], tmp_path / "out.dwg", 0.05)
    assert Path(caught.value.evidence["stdout"]["path"]).is_file()
    assert Path(caught.value.evidence["stderr"]["path"]).is_file()


def test_nonzero_exit_preserves_complete_logs(tmp_path: Path) -> None:
    script = "import sys; print('FULL_STDOUT'); print('FULL_STDERR', file=sys.stderr); sys.exit(7)"
    with pytest.raises(ConversionError, match="exited 7") as caught:
        dwg_adapter.run_fixed_command(Path(sys.executable), ["-c", script], tmp_path / "out.dwg", 2)
    evidence = caught.value.evidence
    assert Path(evidence["stdout"]["path"]).read_text(encoding="utf-8") == "FULL_STDOUT\n"
    assert Path(evidence["stderr"]["path"]).read_text(encoding="utf-8") == "FULL_STDERR\n"
    assert evidence["exit_code"] == 7


def test_exit_zero_without_output_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConversionError, match="did not create"):
        dwg_adapter.run_fixed_command(Path(sys.executable), ["-c", "pass"], tmp_path / "out.dwg", 2)


def test_junk_dwg_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "out.dwg"
    script = f"from pathlib import Path; Path({str(output)!r}).write_bytes(b'x'*64)"
    with pytest.raises(ConversionError, match="not an ACAD2018"):
        dwg_adapter.run_fixed_command(Path(sys.executable), ["-c", script], output, 2)


def test_header_only_dwg_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "out.dwg"
    script = f"from pathlib import Path; Path({str(output)!r}).write_bytes(b'AC1032'+b'x'*64)"
    with pytest.raises(ConversionError, match="header-only"):
        dwg_adapter.run_fixed_command(Path(sys.executable), ["-c", script], output, 2)


def test_header_padded_synthetic_dwg_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "out.dwg"
    script = f"from pathlib import Path; Path({str(output)!r}).write_bytes(b'AC1032'+b'x'*2048)"
    with pytest.raises(ConversionError, match="synthetic or header-padded"):
        dwg_adapter.run_fixed_command(Path(sys.executable), ["-c", script], output, 2)


def test_high_entropy_synthetic_dwg_remains_structure_unverified(tmp_path: Path) -> None:
    output = tmp_path / "out.dwg"
    script = f"from pathlib import Path; Path({str(output)!r}).write_bytes(b'AC1032'+bytes(range(256))*8)"
    with pytest.raises(ConversionError, match="structure is unverified"):
        dwg_adapter.run_fixed_command(Path(sys.executable), ["-c", script], output, 2)


def test_controlled_helper_record_binds_runtime_input_output_and_logs(tmp_path: Path) -> None:
    source = tmp_path / "input.dxf"
    document = ezdxf.new("R2018")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_line((0, 0), (1, 1))
    document.saveas(source)
    output = tmp_path / "out.dxf"
    script = (
        "from pathlib import Path;import shutil;"
        f"shutil.copyfile({str(source)!r},{str(output)!r});print('converted exact input')"
    )
    evidence = dwg_adapter.run_fixed_command(
        Path(sys.executable), ["-c", script], output, 2,
        expected_format="DXF", expected_input=source,
    )
    record = json.loads(Path(evidence["record"]["path"]).read_text(encoding="utf-8"))
    assert record["record_kind"] == "heater_drawing.controlled_execution"
    assert record["schema_version"] == 2
    assert record["executable_sha256"] == dwg_adapter._sha256(Path(sys.executable))
    assert record["input"]["sha256"] == dwg_adapter._sha256(source)
    assert record["output"]["sha256"] == dwg_adapter._sha256(output)
    assert record["output_format"] == "DXF"
    assert record["process_pid"] > 0
    assert dwg_adapter._runtime_execution_error(
        evidence,
        Path(sys.executable),
        (source.resolve(), dwg_adapter._sha256(source)),
        (output.resolve(), dwg_adapter._sha256(output)),
        "DXF",
        require_runtime_provenance=True,
    ) is None
    assert "trusted runtime provenance" in dwg_adapter._runtime_execution_error(
        record,
        Path(sys.executable),
        (source.resolve(), dwg_adapter._sha256(source)),
        (output.resolve(), dwg_adapter._sha256(output)),
        "DXF",
        require_runtime_provenance=True,
    )


def test_runtime_token_is_bound_to_complete_execution_record(tmp_path: Path) -> None:
    source = tmp_path / "input.dxf"
    document = ezdxf.new("R2018")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_line((0, 0), (1, 1))
    document.saveas(source)
    output = tmp_path / "output.dxf"
    script = f"import shutil;shutil.copyfile({str(source)!r},{str(output)!r});print('bound')"
    evidence = dwg_adapter.run_fixed_command(
        Path(sys.executable), ["-c", script], output, 2,
        expected_format="DXF", expected_input=source,
    )
    token = evidence["_runtime_provenance"]

    def check(record, input_path=source, output_path=output):
        return dwg_adapter._runtime_execution_error(
            record,
            Path(sys.executable),
            (input_path.resolve(), dwg_adapter._sha256(input_path)),
            (output_path.resolve(), dwg_adapter._sha256(output_path)),
            "DXF",
            require_runtime_provenance=True,
        )

    def retained_token_copy():
        result = copy.deepcopy({key: value for key, value in evidence.items() if key != "_runtime_provenance"})
        result["_runtime_provenance"] = token
        return result

    mutations = []
    mutations.append(lambda item: item.update(argv=[str(Path(sys.executable).resolve()), "-c", "print('never ran')"]))
    mutations.append(lambda item: item.update(process_pid=12345))
    mutations.append(lambda item: item.update(started_wall_ns=item["started_wall_ns"] - 10))
    mutations.append(lambda item: item["input"].update(mtime_ns=item["input"]["mtime_ns"] + 1))
    mutations.append(lambda item: item["output"].update(size=item["output"]["size"] + 1))
    mutations.append(lambda item: item["stdout"].update(path=str(tmp_path / "other.stdout")))
    mutations.append(lambda item: item["record"].update(sha256="0" * 64))
    for mutate in mutations:
        changed = retained_token_copy()
        mutate(changed)
        assert "changed after the controlled execution" in check(changed)

    rebound_input = tmp_path / "unexecuted-input.dxf"
    rebound_output = tmp_path / "unexecuted-output.dxf"
    rebound_document = ezdxf.new("R2018")
    rebound_document.header["$INSUNITS"] = 4
    rebound_document.modelspace().add_line((4, 5), (8, 9))
    rebound_document.saveas(rebound_input)
    shutil.copyfile(rebound_input, rebound_output)
    rebound = retained_token_copy()
    rebound["argv"] = [str(Path(sys.executable).resolve()), "-c", "print('never ran')"]
    rebound["input"] = dwg_adapter._bound_artifact(rebound_input)
    rebound["output"] = dwg_adapter._bound_artifact(rebound_output)
    assert "changed after the controlled execution" in check(rebound, rebound_input, rebound_output)


def test_runtime_record_rehashes_current_physical_input_and_output(tmp_path: Path) -> None:
    source = tmp_path / "input.dxf"
    document = ezdxf.new("R2018")
    document.modelspace().add_line((0, 0), (10, 10))
    document.saveas(source)
    output = tmp_path / "output.dxf"
    script = f"import shutil;shutil.copyfile({str(source)!r},{str(output)!r});print('bound')"
    evidence = dwg_adapter.run_fixed_command(
        Path(sys.executable), ["-c", script], output, 2,
        expected_format="DXF", expected_input=source,
    )
    source_binding = (source.resolve(), dwg_adapter._sha256(source))
    output_binding = (output.resolve(), dwg_adapter._sha256(output))

    def check():
        return dwg_adapter._runtime_execution_error(
            evidence, Path(sys.executable), source_binding, output_binding, "DXF",
            require_runtime_provenance=True,
        )

    assert check() is None
    for label, path in (("input", source), ("output", output)):
        original = path.read_bytes()
        changed = original.replace(b"10.0", b"11.0", 1)
        assert changed != original and len(changed) == len(original)
        path.write_bytes(changed)
        assert f"exact current runtime {label} bytes" in check()
        path.write_bytes(original)
        assert check() is None

        path.unlink()
        assert f"exact current runtime {label} bytes" in check()
        path.write_bytes(original)
        assert check() is None

        replacement = original[:-1] + bytes([original[-1] ^ 1])
        path.write_bytes(replacement)
        assert f"exact current runtime {label} bytes" in check()
        path.write_bytes(original)
        assert check() is None


def test_runtime_version_token_is_bound_to_complete_record(tmp_path: Path) -> None:
    launcher = tmp_path / ("ODAFileConverter.cmd" if sys.platform == "win32" else "ODAFileConverter")
    if sys.platform == "win32":
        launcher.write_text("@echo ODA File Converter fixture\n", encoding="utf-8")
    else:
        launcher.write_text(f"#!{sys.executable}\nprint('ODA File Converter fixture')\n", encoding="utf-8")
        launcher.chmod(0o700)
    evidence = dwg_adapter.run_version_command(launcher, 2, tmp_path / "logs")
    assert dwg_adapter._runtime_version_error(
        evidence, launcher, require_runtime_provenance=True
    ) is None
    changed = copy.deepcopy({key: value for key, value in evidence.items() if key != "_runtime_provenance"})
    changed["_runtime_provenance"] = evidence["_runtime_provenance"]
    changed["stderr"]["sha256"] = "0" * 64
    assert "changed after the controlled execution" in dwg_adapter._runtime_version_error(
        changed, launcher, require_runtime_provenance=True
    )


def test_imported_command_record_cannot_override_its_runtime_input_binding(tmp_path: Path) -> None:
    converter = Path(sys.executable).resolve()
    source = tmp_path / "input.dxf"
    source.write_bytes(b"exact input")
    output = tmp_path / "output.dwg"
    output.write_bytes(b"AC1032" + bytes(range(256)) * 8)
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    stdout.write_text("claimed conversion\n", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    def artifact(path: Path) -> dict:
        return {"path": str(path.resolve()), "sha256": dwg_adapter._sha256(path)}

    argv = [
        str(converter), str(source.parent.resolve()), str(output.parent.resolve()),
        "ACAD2018", "DWG", "0", "1", source.name,
    ]
    now = __import__("time").time_ns()
    record = {
        "schema_version": 2,
        "record_kind": "heater_drawing.controlled_execution",
        "argv": argv,
        "status": "passed",
        "exit_code": 0,
        "executable_path": str(converter),
        "executable_sha256": dwg_adapter._sha256(converter),
        "process_pid": 12345,
        "output_format": "DWG",
        "started_wall_ns": now - 1_000_000,
        "finished_wall_ns": now,
        "started_monotonic_ns": 10_000_000,
        "finished_monotonic_ns": 11_000_000,
        "input": {"path": "/not/the/input.dxf", "sha256": "0" * 64, "size": source.stat().st_size},
        "output": {**artifact(output), "size": output.stat().st_size},
        "stdout": artifact(stdout),
        "stderr": artifact(stderr),
    }
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    item = {
        "argv": argv,
        "exit_code": 0,
        "input_path": str(source.resolve()),
        "input_sha256": dwg_adapter._sha256(source),
        "output_path": str(output.resolve()),
        "output_sha256": dwg_adapter._sha256(output),
        "stdout": artifact(stdout),
        "stderr": artifact(stderr),
        "record": artifact(record_path),
    }
    error = dwg_adapter._command_evidence(
        item,
        converter,
        (source.resolve(), dwg_adapter._sha256(source)),
        (output.resolve(), dwg_adapter._sha256(output)),
        "forward",
    )
    assert error is not None
    assert "outer command summary" in error or "exact runtime input" in error


def test_imported_complete_command_record_remains_unverified(tmp_path: Path) -> None:
    converter = Path(sys.executable).resolve()
    source = tmp_path / "input.dxf"
    source.write_bytes(b"exact input")
    output = tmp_path / "output.dwg"
    output.write_bytes(b"AC1032" + bytes(range(256)) * 8)
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    stdout.write_text("claimed conversion\n", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    def artifact(path: Path) -> dict:
        return {"path": str(path.resolve()), "sha256": dwg_adapter._sha256(path)}

    argv = [str(converter), str(source.parent.resolve()), str(output.parent.resolve()), "ACAD2018", "DWG", "0", "1", source.name]
    now = __import__("time").time_ns()
    record = {
        "schema_version": 2, "record_kind": "heater_drawing.controlled_execution",
        "argv": argv, "status": "passed", "exit_code": 0,
        "executable_path": str(converter), "executable_sha256": dwg_adapter._sha256(converter),
        "process_pid": 12345, "output_format": "DWG",
        "started_wall_ns": now - 1_000_000, "finished_wall_ns": now,
        "started_monotonic_ns": 10_000_000, "finished_monotonic_ns": 11_000_000,
        "input": {**artifact(source), "size": source.stat().st_size},
        "output": {**artifact(output), "size": output.stat().st_size},
        "stdout": artifact(stdout), "stderr": artifact(stderr),
    }
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    item = {
        "argv": argv, "exit_code": 0,
        "input_path": str(source.resolve()), "input_sha256": dwg_adapter._sha256(source),
        "output_path": str(output.resolve()), "output_sha256": dwg_adapter._sha256(output),
        "stdout": artifact(stdout), "stderr": artifact(stderr), "record": artifact(record_path),
    }
    error = dwg_adapter._command_evidence(item, converter, (source.resolve(), dwg_adapter._sha256(source)), (output.resolve(), dwg_adapter._sha256(output)), "forward")
    assert error == "forward imported command record has no trusted runtime provenance"


def test_inverted_imported_version_timing_is_rejected(tmp_path: Path) -> None:
    converter = Path(sys.executable).resolve()
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    stdout.write_text("ODA File Converter fabricated\n", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    def artifact(path: Path) -> dict:
        return {"path": str(path.resolve()), "sha256": dwg_adapter._sha256(path)}

    record = {
        "schema_version": 2,
        "record_kind": "heater_drawing.controlled_version_execution",
        "argv": [str(converter), "--version"],
        "status": "passed",
        "exit_code": 0,
        "executable_path": str(converter),
        "executable_sha256": dwg_adapter._sha256(converter),
        "process_pid": 12345,
        "started_wall_ns": 999,
        "finished_wall_ns": 0,
        "started_monotonic_ns": 999,
        "finished_monotonic_ns": 0,
        "stdout": artifact(stdout),
        "stderr": artifact(stderr),
    }
    record_path = tmp_path / "version.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    receipt = {"stdout": artifact(stdout), "stderr": artifact(stderr), "record": artifact(record_path)}
    assert "timing is inverted" in dwg_adapter._version_execution_error(receipt, converter)


def test_stale_output_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "out.dwg"
    output.write_bytes(b"AC1032" + b"x" * 64)
    with pytest.raises(ConversionError, match="stale"):
        dwg_adapter.run_fixed_command(Path(sys.executable), ["-c", "pass"], output, 2)


def test_missing_glyph_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "font.ttf"
    path.write_bytes(b"not-used")
    monkeypatch.setattr(fonts, "supported_codepoints", lambda _path, _face_index=None: {ord("A")})
    with pytest.raises(fonts.GlyphCoverageError, match=r"U\+03A9"):
        fonts.check_glyph_coverage(path, ["AΩ"])


def test_collection_coverage_requires_exact_face() -> None:
    profile = json.loads((ROOT / "templates/heater-a4-v1/fonts.json").read_text(encoding="utf-8"))
    path = Path(profile["source_collection_path"])
    if not path.is_file():
        runtime = ROOT / profile["render_font_path"]
        assert hashlib.sha256(runtime.read_bytes()).hexdigest() == profile["extracted_face_sha256"]
        assert ord("郑") in fonts.supported_codepoints(runtime)
        return
    with pytest.raises(fonts.GlyphCoverageError, match="exact face index"):
        fonts.supported_codepoints(path)
    assert ord("郑") in fonts.supported_codepoints(path, 2)


def test_invalid_template_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "layout.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    (tmp_path / "fonts.json").write_text(json.dumps({"cad_text_mode": "editable_text"}), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    (tmp_path / "template.dxf").write_text("not a dxf", encoding="utf-8")
    with pytest.raises(TemplateError, match="lacks keys"):
        load_template(tmp_path)


def test_controlled_template_dxf_hash_is_checked(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "templates/heater-a4-v1", tmp_path, dirs_exist_ok=True)
    (tmp_path / "template.dxf").write_text("not a DXF", encoding="utf-8")
    with pytest.raises(TemplateError, match="controlled hash mismatch: template.dxf"):
        load_template(tmp_path)


def _sample_dxf(tmp_path: Path, index: int = 0) -> tuple[Path, DrawingPage, dict]:
    template = load_template(ROOT / "templates/heater-a4-v1")
    _, pages = load_sample(ROOT / "fixtures/synthetic/heater_sample.json")
    page = pages[index]
    path = tmp_path / "sample.dxf"
    write_page_dxf(path, page, template["layout"], template["fonts"])
    return path, page, template["layout"]


def _must_reject(tmp_path: Path, mutation, match: str, index: int = 0) -> None:
    path, page, layout = _sample_dxf(tmp_path, index)
    doc = ezdxf.readfile(path)
    mutation(doc, page)
    doc.saveas(path)
    with pytest.raises(ReadbackError, match=match):
        inspect_dxf(path, [page], layout)


def _template_identity(entity) -> tuple[str, ...]:
    try:
        return tuple(
            str(value)
            for code, value in entity.get_xdata("HEATER_DRAWING")
            if code == 1000
        )
    except ezdxf.DXFValueError:
        return ()


def _native_frame_lines(doc, *, yellow: bool | None = None) -> list:
    lines = [
        entity
        for entity in doc.modelspace().query("LINE")
        if _template_identity(entity)[:2] == ("template", "frame-line")
    ]
    if yellow is None:
        return lines
    return [
        entity
        for entity in lines
        if (entity.dxf.get("true_color", None) == 16308017) is yellow
    ]


def test_unit_drift_is_rejected(tmp_path: Path) -> None:
    _must_reject(tmp_path, lambda doc, _page: doc.header.__setitem__("$INSUNITS", 1), "unit drift")


def test_native_dimension_loss_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        doc.modelspace().delete_entity(next(iter(doc.modelspace().query("DIMENSION"))))
    _must_reject(tmp_path, mutate, "entity count mismatch")


def test_dimension_display_override_is_rejected(tmp_path: Path) -> None:
    _must_reject(tmp_path, lambda doc, _page: setattr(next(iter(doc.modelspace().query("DIMENSION"))).dxf, "text", "999"), "display override")


def test_text_style_font_substitution_is_rejected(tmp_path: Path) -> None:
    _must_reject(tmp_path, lambda doc, _page: setattr(doc.styles.get("HEATER_CJK").dxf, "font", "arial.ttf"), "font filename drift")


@pytest.mark.parametrize(
    "attribute,value,match",
    [
        ("font", "arial.ttf", "original HZ SHX style dependency drift"),
        ("bigfont", "other.shx", "original HZ SHX style dependency drift"),
        ("width", 1.0, "original HZ effective display properties drift"),
    ],
)
def test_original_hz_style_drift_is_rejected(
    tmp_path: Path, attribute: str, value, match: str
) -> None:
    _must_reject(
        tmp_path,
        lambda doc, _page: setattr(doc.styles.get("HZ").dxf, attribute, value),
        match,
    )


def test_dimension_style_text_style_substitution_is_rejected(tmp_path: Path) -> None:
    _must_reject(tmp_path, lambda doc, _page: setattr(doc.dimstyles.get("HEATER_DIM").dxf, "dimtxsty", "Standard"), "text-style association drift")


def test_dimension_cached_display_mutation_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        cached = next(iter(doc.blocks.get(dimension.dxf.geometry).query("MTEXT")))
        cached.text = "999"
    _must_reject(tmp_path, mutate, "cached display text drift")


def test_wrong_viewport_scale_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, page):
        viewport = next(v for v in doc.layouts.get(page.code).query("VIEWPORT") if v.has_xdata("HEATER_DRAWING"))
        viewport.dxf.view_height = 100
    _must_reject(tmp_path, mutate, "viewport scale drift", index=2)


def test_dimension_multiplier_drift_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        override = next(iter(doc.modelspace().query("DIMENSION"))).override()
        override.update({"dimlfac": 10})
        override.render()
    _must_reject(tmp_path, mutate, "dimension style/display multiplier drift")


@pytest.mark.parametrize("field", ["dimltype", "dimltex1", "dimltex2"])
def test_dimension_style_regeneration_linetype_source_is_rejected(
    tmp_path: Path, field: str
) -> None:
    def mutate(doc, _page):
        doc.linetypes.add("TEST_DASHED", pattern=[10.0, 5.0, -5.0])
        setattr(doc.dimstyles.get("HEATER_DIM").dxf, field, "TEST_DASHED")

    _must_reject(tmp_path, mutate, "dimension linetype source is outside")


@pytest.mark.parametrize("field", ["dimltype", "dimltex1", "dimltex2"])
def test_dimension_override_regeneration_linetype_source_is_rejected(
    tmp_path: Path, field: str
) -> None:
    def mutate(doc, _page):
        doc.linetypes.add("TEST_DASHED", pattern=[10.0, 5.0, -5.0])
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        values = dimension.get_acad_dstyle(
            doc.dimstyles.get(dimension.dxf.dimstyle)
        )
        dimension.set_acad_dstyle({**values, field: "TEST_DASHED"})

    _must_reject(tmp_path, mutate, "dimension linetype source is outside")


@pytest.mark.parametrize("field", ["dimltype", "dimltex1", "dimltex2"])
@pytest.mark.parametrize("source", ["dimstyle", "override"])
def test_explicit_continuous_dimension_linetype_source_survives_regeneration(
    tmp_path: Path, source: str, field: str
) -> None:
    path, page, layout = _sample_dxf(tmp_path)
    template = load_template(ROOT / "templates/heater-a4-v1")
    document = ezdxf.readfile(path)
    dimension = next(iter(document.modelspace().query("DIMENSION")))
    dimstyle = document.dimstyles.get(dimension.dxf.dimstyle)
    if source == "dimstyle":
        setattr(dimstyle.dxf, field, "Continuous")
    else:
        values = dimension.get_acad_dstyle(dimstyle)
        dimension.set_acad_dstyle({**values, field: "Continuous"})
    for item in document.modelspace().query("DIMENSION"):
        item.render()
    document.saveas(path)
    report = inspect_dxf(path, [page], layout, template["fonts"])
    signature = report["pages"][0]["dimension_linetype_sources"]["width"]
    assert signature["fields"][field]["source"] == "Continuous"
    assert signature["fields"][field]["effective_linetype"] == "Continuous"
    assert controlled_dimension_linetype_signature(
        document, dimension
    )["fields"][field]["linetype_definition"]["compiled_pattern"] == []
    font_path = fonts.prepare_runtime_font(template["fonts"], ROOT)
    rendered = render_page(
        path,
        tmp_path / f"{source}-{field}.pdf",
        tmp_path / f"{source}-{field}.png",
        float(page.scale.denominator),
        font_path,
        template["fonts"],
    )
    assert rendered["native_dimensions"] == 2


def test_viewport_twist_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, page):
        viewport = next(v for v in doc.layouts.get(page.code).query("VIEWPORT") if v.has_xdata("HEATER_DRAWING"))
        viewport.dxf.view_twist_angle = 45
    _must_reject(tmp_path, mutate, "viewport twist drift")


def test_paper_width_drift_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, page):
        doc.layouts.get(page.code).dxf.paper_width = 420
    _must_reject(tmp_path, mutate, "paper size drift")


def test_text_alignment_drift_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        next(iter(doc.modelspace().query("TEXT"))).dxf.halign = 2
    _must_reject(tmp_path, mutate, "text alignment drift")


def test_text_oblique_drift_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        next(iter(doc.modelspace().query("TEXT"))).dxf.oblique = 40
    _must_reject(tmp_path, mutate, "effective display properties drift")


@pytest.mark.parametrize("attribute,value", [("oblique", 40.0), ("width", 0.3)])
def test_text_style_effective_property_drift_is_rejected(
    tmp_path: Path, attribute: str, value: float
) -> None:
    def mutate(doc, _page):
        setattr(doc.styles.get("HEATER_CJK").dxf, attribute, value)
    _must_reject(tmp_path, mutate, "HEATER_CJK effective display properties drift")


def test_dimension_cached_rotation_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        cached = next(iter(doc.blocks.get(dimension.dxf.geometry).query("MTEXT")))
        cached.dxf.rotation = 45
    _must_reject(tmp_path, mutate, "cached display orientation drift")


def test_dimension_cached_and_midpoint_synchronized_shift_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        dimension.dxf.text_midpoint = dimension.dxf.text_midpoint + (20, 0, 0)
        cached = next(iter(doc.blocks.get(dimension.dxf.geometry).query("MTEXT")))
        cached.dxf.insert = cached.dxf.insert + (20, 0, 0)
    _must_reject(tmp_path, mutate, "dimension text midpoint drift")


def test_dimension_arrow_scale_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        arrow = next(iter(doc.blocks.get(dimension.dxf.geometry).query("INSERT")))
        arrow.dxf.xscale = 0.1
        arrow.dxf.yscale = 0.1
    _must_reject(tmp_path, mutate, "dimension arrow geometry drift")


def test_dimension_arrow_block_vertices_are_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        block = doc.blocks.get("_CLOSEDFILLED")
        for solid in block.query("SOLID"):
            for name in ("vtx0", "vtx1", "vtx2", "vtx3"):
                setattr(solid.dxf, name, solid.dxf.get(name) * 0.1)

    _must_reject(tmp_path, mutate, "complete visible cache semantics drift")


def test_dimension_cached_inline_format_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        cached = next(iter(doc.blocks.get(dimension.dxf.geometry).query("MTEXT")))
        cached.text = "{\\W0.2;25}"

    _must_reject(tmp_path, mutate, "complete visible cache semantics drift")


def test_dimension_cached_line_geometry_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        line = next(iter(doc.blocks.get(dimension.dxf.geometry).query("LINE")))
        line.dxf.start = (80, 185, 0)

    _must_reject(tmp_path, mutate, "complete visible cache semantics drift")


@pytest.mark.parametrize(
    "kind,mutation",
    [
        ("mtext-invisible", lambda doc, cache: setattr(next(iter(cache.query("MTEXT"))).dxf, "invisible", 1)),
        ("line-invisible", lambda doc, cache: setattr(next(iter(cache.query("LINE"))).dxf, "invisible", 1)),
        (
            "solid-true-color",
            lambda doc, _cache: [
                setattr(entity.dxf, "true_color", 0xFFFFFF)
                for entity in doc.blocks.get("_CLOSEDFILLED").query("SOLID")
            ],
        ),
        (
            "mtext-extrusion",
            lambda doc, cache: setattr(next(iter(cache.query("MTEXT"))).dxf, "extrusion", (0, 0, -1)),
        ),
        (
            "mtext-background",
            lambda doc, cache: next(iter(cache.query("MTEXT"))).set_bg_color(7, scale=4),
        ),
        (
            "line-thickness",
            lambda doc, cache: setattr(next(iter(cache.query("LINE"))).dxf, "thickness", 10),
        ),
    ],
)
def test_dimension_cache_effective_display_mutations_are_rejected(
    tmp_path: Path, kind: str, mutation
) -> None:
    def mutate(doc, _page):
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        mutation(doc, doc.blocks.get(dimension.dxf.geometry))

    _must_reject(tmp_path, mutate, "complete visible cache semantics drift")


def test_dimension_entity_extrusion_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        next(iter(doc.modelspace().query("DIMENSION"))).dxf.extrusion = (0, 0, -1)

    _must_reject(tmp_path, mutate, "dimension effective display properties drift")


@pytest.mark.parametrize(
    "kind,mutation",
    [
        ("dimension-color", lambda doc, dim: setattr(dim.dxf, "color", 2)),
        ("dimension-lineweight", lambda doc, dim: setattr(dim.dxf, "lineweight", 211)),
        ("layer-off", lambda doc, dim: doc.layers.get("DIMENSION").off()),
        ("layer-frozen", lambda doc, dim: doc.layers.get("DIMENSION").freeze()),
        ("layer-true-color", lambda doc, dim: setattr(doc.layers.get("DIMENSION").dxf, "true_color", 0xFFFFFF)),
        ("layer-transparency", lambda doc, dim: setattr(doc.layers.get("DIMENSION"), "transparency", 1.0)),
        ("layer-color", lambda doc, dim: setattr(doc.layers.get("DIMENSION").dxf, "color", 2)),
        (
            "combined-inheritance",
            lambda doc, dim: (
                doc.layers.get("DIMENSION").off(),
                setattr(doc.layers.get("DIMENSION").dxf, "true_color", 0xFFFFFF),
                setattr(dim.dxf, "color", 256),
            ),
        ),
    ],
)
def test_dimension_parent_and_layer_display_inheritance_is_rejected(
    tmp_path: Path, kind: str, mutation
) -> None:
    def mutate(doc, _page):
        dimension = next(iter(doc.modelspace().query("DIMENSION")))
        mutation(doc, dimension)

    _must_reject(tmp_path, mutate, "display")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda doc, dim: setattr(dim.dxf, "color", 2),
        lambda doc, dim: setattr(dim.dxf, "lineweight", 211),
        lambda doc, dim: doc.layers.get("DIMENSION").off(),
        lambda doc, dim: doc.layers.get("DIMENSION").freeze(),
        lambda doc, dim: setattr(doc.layers.get("DIMENSION").dxf, "true_color", 0xFFFFFF),
        lambda doc, dim: setattr(doc.layers.get("DIMENSION"), "transparency", 1.0),
        lambda doc, dim: setattr(doc.layers.get("DIMENSION").dxf, "color", 2),
    ],
)
def test_renderer_rejects_dimension_parent_and_layer_display_drift(
    tmp_path: Path, mutation
) -> None:
    path, page, _layout = _sample_dxf(tmp_path)
    template = load_template(ROOT / "templates/heater-a4-v1")
    document = ezdxf.readfile(path)
    dimension = next(iter(document.modelspace().query("DIMENSION")))
    mutation(document, dimension)
    document.saveas(path)
    font_path = fonts.prepare_runtime_font(template["fonts"], ROOT)
    with pytest.raises(RenderError, match="display"):
        render_page(
            path, tmp_path / "wrong.pdf", tmp_path / "wrong.png",
            float(page.scale.denominator), font_path, template["fonts"],
        )


@pytest.mark.parametrize("pattern", [[10.0, 5.0, -5.0], [1.0, 0.5, -0.5]])
def test_referenced_continuous_linetype_pattern_is_rejected(
    tmp_path: Path, pattern: list[float]
) -> None:
    def mutate(doc, _page):
        doc.linetypes.get("Continuous").setup_pattern(pattern)

    _must_reject(tmp_path, mutate, "controlled linetype definition drift")


def test_referenced_complex_continuous_linetype_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        doc.linetypes.get("Continuous").setup_pattern(
            'A,.5,-.25,["GAS",STANDARD,S=.1,R=0.0,X=-0.1,Y=-.05],-.25'
        )

    _must_reject(tmp_path, mutate, "controlled linetype definition drift")


def test_renderer_rejects_referenced_continuous_linetype_pattern(
    tmp_path: Path,
) -> None:
    path, page, _layout = _sample_dxf(tmp_path)
    template = load_template(ROOT / "templates/heater-a4-v1")
    document = ezdxf.readfile(path)
    document.linetypes.get("Continuous").setup_pattern([10.0, 5.0, -5.0])
    document.saveas(path)
    font_path = fonts.prepare_runtime_font(template["fonts"], ROOT)
    with pytest.raises(RenderError, match="controlled linetype definition drift"):
        render_page(
            path, tmp_path / "wrong.pdf", tmp_path / "wrong.png",
            float(page.scale.denominator), font_path, template["fonts"],
        )


@pytest.mark.parametrize("pattern", [[0.0], [3e-14]])
def test_continuous_linetype_explicit_default_and_noise_are_normalized(
    tmp_path: Path, pattern: list[float]
) -> None:
    path, page, layout = _sample_dxf(tmp_path)
    original = ezdxf.readfile(path)
    expected_signature = controlled_layer_signature(original)
    document = ezdxf.readfile(path)
    document.linetypes.get("Continuous").setup_pattern(pattern)
    document.saveas(path)
    assert controlled_layer_error(document) is None
    assert controlled_layer_signature(document) == expected_signature
    assert inspect_dxf(path, [page], layout)["status"] == "passed"


def test_unused_linetype_definition_does_not_expand_controlled_profile(
    tmp_path: Path,
) -> None:
    path, page, layout = _sample_dxf(tmp_path)
    document = ezdxf.readfile(path)
    document.linetypes.add("UNUSED_DASHED", pattern=[1.0, 0.5, -0.5])
    document.saveas(path)
    assert controlled_layer_error(document) is None
    assert inspect_dxf(path, [page], layout)["status"] == "passed"


def test_dimension_cache_explicit_display_defaults_equal_omitted_defaults(tmp_path: Path) -> None:
    path, page, layout = _sample_dxf(tmp_path)
    template = load_template(ROOT / "templates/heater-a4-v1")
    document = ezdxf.readfile(path)
    dimension = next(iter(document.modelspace().query("DIMENSION")))
    cache = document.blocks.get(dimension.dxf.geometry)
    for entity in cache:
        for name, value in (
            ("invisible", 0), ("ltscale", 1.0), ("lineweight", -1),
            ("thickness", 0.0), ("extrusion", (0.0, 0.0, 1.0)),
        ):
            if entity.dxf.is_supported(name):
                setattr(entity.dxf, name, value)
    cached_text = next(iter(cache.query("MTEXT")))
    cached_text.dxf.bg_fill = 0
    cached_text.dxf.box_fill_scale = 1.5
    explicit = tmp_path / "explicit-defaults.dxf"
    document.saveas(explicit)
    assert inspect_dxf(explicit, [page], layout, template["fonts"])["status"] == "passed"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda entity: setattr(entity.dxf, "invisible", 1),
        lambda entity: setattr(entity.dxf, "extrusion", (0, 0, -1)),
        lambda entity: setattr(entity.dxf, "thickness", 10),
    ],
)
def test_renderer_rejects_display_extensions_outside_controlled_profile(
    tmp_path: Path, mutation
) -> None:
    path, page, _layout = _sample_dxf(tmp_path)
    template = load_template(ROOT / "templates/heater-a4-v1")
    document = ezdxf.readfile(path)
    dimension = next(iter(document.modelspace().query("DIMENSION")))
    mutation(next(iter(document.blocks.get(dimension.dxf.geometry).query("LINE"))))
    document.saveas(path)
    font_path = fonts.prepare_runtime_font(template["fonts"], ROOT)
    with pytest.raises(RenderError, match="controlled renderer profile"):
        render_page(
            path, tmp_path / "wrong.pdf", tmp_path / "wrong.png",
            float(page.scale.denominator), font_path, template["fonts"],
        )


def test_dimension_cache_survives_explicit_regeneration_and_reopen(tmp_path: Path) -> None:
    path, page, layout = _sample_dxf(tmp_path)
    template = load_template(ROOT / "templates/heater-a4-v1")
    document = ezdxf.readfile(path)
    for dimension in document.modelspace().query("DIMENSION"):
        dimension.render()
    regenerated = tmp_path / "regenerated.dxf"
    document.saveas(regenerated)
    report = inspect_dxf(regenerated, [page], layout, template["fonts"])
    assert report["pages"][0]["dimension_regeneration_semantics"].startswith("matches")


def test_pdf_frame_colors_follow_controlled_layer_policy(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("probe_formats_colors", ROOT / "scripts/probe_formats.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dxf, page, layout = _sample_dxf(tmp_path)
    template = load_template(ROOT / "templates/heater-a4-v1")
    font_path = fonts.prepare_runtime_font(template["fonts"], ROOT)
    pdf = tmp_path / "colored.pdf"
    render_page(dxf, pdf, tmp_path / "colored.png", float(page.scale.denominator), font_path, template["fonts"])
    assert module.validate_pdf_page(pdf, page, layout)["expected_text_entities"] == 33
    result = module.validate_pdf_frame_colors(pdf, layout)
    expected_yellow = sum(line[6] == 16308017 for line in layout["frame_lines_mm"])
    assert result["yellow_segments"] == expected_yellow
    assert result["black_segments"] == len(layout["frame_lines_mm"]) - expected_yellow

    document = ezdxf.readfile(dxf)
    yellow_line = _native_frame_lines(document, yellow=True)[0]
    yellow_line.dxf.true_color = 0xFFFFFF
    wrong_dxf = tmp_path / "wrong-color.dxf"
    document.saveas(wrong_dxf)
    wrong_pdf = tmp_path / "wrong-color.pdf"
    with pytest.raises(RenderError, match="native yellow frame display binding drift"):
        render_page(
            wrong_dxf, wrong_pdf, tmp_path / "wrong-color.png",
            float(page.scale.denominator), font_path, template["fonts"],
        )


def test_removed_frames_are_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        doc.modelspace().delete_entity(_native_frame_lines(doc)[0])
    _must_reject(tmp_path, mutate, "controlled native frame entity count mismatch")


@pytest.mark.parametrize("yellow", [False, True])
def test_native_frame_layer_drift_is_rejected(tmp_path: Path, yellow: bool) -> None:
    def mutate(doc, _page):
        _native_frame_lines(doc, yellow=yellow)[0].dxf.layer = "text"
    _must_reject(tmp_path, mutate, "native frame layer binding drift")


@pytest.mark.parametrize("yellow", [False, True])
def test_native_frame_entity_display_drift_is_rejected(
    tmp_path: Path, yellow: bool
) -> None:
    def mutate(doc, _page):
        _native_frame_lines(doc, yellow=yellow)[0].dxf.lineweight = 50
    _must_reject(tmp_path, mutate, "native .* frame display binding drift")


def test_native_yellow_frame_true_color_drift_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        _native_frame_lines(doc, yellow=True)[0].dxf.true_color = 0xFFFFFF
    _must_reject(tmp_path, mutate, "native yellow frame display binding drift")


def test_native_frame_position_drift_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        _native_frame_lines(doc)[0].translate(0.5, 0.0, 0.0)
    _must_reject(tmp_path, mutate, "controlled frame line missing/drifted")


def test_dimension_virtual_text_uses_locked_style(tmp_path: Path) -> None:
    path, page, layout = _sample_dxf(tmp_path)
    report = inspect_dxf(path, [page], layout)
    document = ezdxf.readfile(path)
    for dimension in document.modelspace().query("DIMENSION"):
        texts = [entity for entity in dimension.virtual_entities() if entity.dxftype() in {"TEXT", "MTEXT"}]
        assert len(texts) == 1
        assert texts[0].dxf.style == "HEATER_CJK"
    assert report["pages"][0]["complete_content_box_paper_mm"]


def test_all_text_insertions_are_inside_paper(tmp_path: Path) -> None:
    path, page, layout = _sample_dxf(tmp_path, 2)
    report = inspect_dxf(path, [page], layout)
    measurements = report["pages"][0]["text_measurements"]
    assert measurements
    for index, item in enumerate(measurements):
        x, y = item["point_paper_mm"]
        assert 0.0 <= x <= 210.0
        assert 0.0 <= y <= 297.0
        left, bottom, right, top = item["box_paper_mm"]
        assert left < right and bottom < top
        assert 0.0 <= left < right <= 210.0
        assert 0.0 <= bottom < top <= 297.0
        if item["cell_mm"] is not None:
            tolerance = 0.25 if item["identity"].endswith("/technical/0") else 0.1
            cell = item["cell_mm"]
            assert left >= cell[0] - tolerance
            assert bottom >= cell[1] - tolerance
            assert right <= cell[2] + tolerance
            assert top <= cell[3] + tolerance
        expected = next(
            record
            for record in expected_text_records(layout, page)
            if f"{page.row_id}/{record['kind']}/{record['id']}" == item["identity"]
        )
        assert item["frame_crossings"] == expected.get("allowed_frame_crossings", [])
        for other in measurements[index + 1:]:
            other_box = other["box_paper_mm"]
            assert min(right, other_box[2]) - max(left, other_box[0]) <= 0.01 or min(
                top, other_box[3]
            ) - max(bottom, other_box[1]) <= 0.01


def test_native_mtext_raw_formatting_is_preserved(tmp_path: Path) -> None:
    path, page, layout = _sample_dxf(tmp_path)
    report = inspect_dxf(path, [page], layout)
    document = ezdxf.readfile(path)
    organization = next(
        entity
        for entity in document.modelspace().query("MTEXT")
        if _template_identity(entity)[1:] == ("field", "organization")
    )
    name = next(
        entity
        for entity in document.modelspace().query("MTEXT")
        if _template_identity(entity)[1:] == ("field", "name")
    )
    assert organization.text.startswith("\\pxqc;{\\H1.042x;")
    assert organization.text.endswith("}")
    assert page.fields.organization in organization.text
    assert name.text.startswith("\\pxqc;{\\H1.042x;")
    assert report["pages"][0]["text_measurements"]


@pytest.mark.parametrize("control", ["\\H3x;", "\\W3;", "\\C1;"])
def test_mtext_effective_format_mutations_are_rejected(
    tmp_path: Path, control: str
) -> None:
    def mutate(doc, _page):
        entity = next(
            item
            for item in doc.modelspace().query("MTEXT")
            if _template_identity(item)[1:] == ("field", "organization")
        )
        entity.text = "{" + control + entity.text + "}"

    _must_reject(tmp_path, mutate, "MTEXT effective format drift")


def test_mtext_flow_direction_mutation_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        entity = next(
            item
            for item in doc.modelspace().query("MTEXT")
            if _template_identity(item)[1:] == ("field", "organization")
        )
        entity.dxf.flow_direction = 3

    _must_reject(tmp_path, mutate, "MTEXT layout drift")


def test_mtext_harmless_effective_defaults_are_accepted(tmp_path: Path) -> None:
    path, page, layout = _sample_dxf(tmp_path)
    document = ezdxf.readfile(path)
    entity = next(
        item
        for item in document.modelspace().query("MTEXT")
        if _template_identity(item)[1:] == ("field", "organization")
    )
    entity.text = "{\\H1x;\\W1;" + entity.text + "}"
    document.saveas(path)
    report = inspect_dxf(path, [page], layout)
    measurement = next(
        item
        for item in report["pages"][0]["text_measurements"]
        if item["identity"].endswith("/field/organization")
    )
    assert measurement["effective_format"]


def test_pdf_native_dimension_vectors_remain_one_to_one(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "probe_formats_dimensions", ROOT / "scripts/probe_formats.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = load_template(ROOT / "templates/heater-a4-v1")
    dxf, page, layout = _sample_dxf(tmp_path)
    report = inspect_dxf(dxf, [page], layout, template["fonts"])
    font_path = fonts.prepare_runtime_font(template["fonts"], ROOT)
    pdf = tmp_path / "dimension-scale.pdf"
    render_page(
        dxf,
        pdf,
        tmp_path / "dimension-scale.png",
        float(page.scale.denominator),
        font_path,
        template["fonts"],
    )
    result = module.validate_pdf_dimension_text_vectors(
        pdf, report["pages"][0]["dimension_text_measurements"]
    )
    for measurement in result["dimensions"].values():
        assert measurement["actual_to_native_width_ratio"] == pytest.approx(1.0, abs=0.02)
        assert measurement["actual_to_native_height_ratio"] == pytest.approx(1.0, abs=0.02)


def test_moved_lead_is_rejected(tmp_path: Path) -> None:
    _must_reject(tmp_path, lambda doc, _page: next(iter(doc.modelspace().query("LINE[layer=='HEATER_LEAD']"))).translate(1000, 1000, 0), "lead start")


def test_changed_resistance_text_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        entity = next(
            e
            for e in doc.modelspace().query("TEXT MTEXT")
            if "R=23.52" in (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text)
        )
        if entity.dxftype() == "MTEXT":
            entity.text = "R=999"
        else:
            entity.dxf.text = "R=999"
    _must_reject(tmp_path, mutate, "text value drift")


def test_triangle_with_same_bounds_is_rejected(tmp_path: Path) -> None:
    def mutate(doc, _page):
        heater = next(iter(doc.modelspace().query("LWPOLYLINE[layer=='HEATER']")))
        points = list(heater.get_points("xy"))
        heater.set_points([points[0], points[1], points[2]])
    _must_reject(tmp_path, mutate, "exactly four straight corners")


def test_unknown_entity_is_rejected(tmp_path: Path) -> None:
    _must_reject(tmp_path, lambda doc, _page: doc.modelspace().add_circle((0, 0), 1), "unsupported modelspace")


def test_long_side_length_dimension_is_on_right(tmp_path: Path) -> None:
    path, page, layout = _sample_dxf(tmp_path, 1)
    report = inspect_dxf(path, [page], layout)
    doc = ezdxf.readfile(path)
    rectangle = page.geometry_mm.rectangle
    right = float(rectangle.origin.x) + float(rectangle.width_mm)
    dimension = next(e for e in doc.modelspace().query("DIMENSION") if "length" in [str(v) for c, v in e.get_xdata("HEATER_DRAWING") if c == 1000])
    assert dimension.dxf.defpoint.x > right
    assert report["dimension_arrow_solids"] == 4


def test_three_pages_are_public_c02_contracts() -> None:
    _, pages = load_sample(ROOT / "fixtures/synthetic/heater_sample.json")
    for page in pages:
        payload = page.model_dump(mode="json")
        assert DrawingPage.model_validate(payload) == page
        assert validate_contract_semantics("drawing-page.schema.json", payload) == page


def test_gate_rejects_empty_and_synthetic_approval() -> None:
    spec = importlib.util.spec_from_file_location("format_gate", ROOT / "scripts/check_format_gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    probe = {"timestamp": "2026-11-07T00:00:00+00:00", "candidate": "docs/evidence/B02-fix-1/candidate", "validated_candidate_hashes": {}}
    assert module.validate_approval({"status": "approved"}, probe)
    assert any("test-only" in error for error in module.validate_approval({"status": "approved", "actor": "SYNTHETIC_ONLY"}, probe))


def test_structured_cad_approval_binds_exact_candidate_and_rejects_hollow_fixture(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("format_gate_structured", ROOT / "scripts/check_format_gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path

    candidate = tmp_path / "candidate" / "input.dxf"
    output = tmp_path / "cad" / "reopened.dxf"
    screenshot = tmp_path / "cad" / "screen.png"
    record_path = tmp_path / "cad" / "record.json"
    candidate.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    for path in (candidate, output):
        document = ezdxf.new("R2018")
        document.header["$INSUNITS"] = 4
        document.modelspace().add_line((0, 0), (1, 1))
        document.saveas(path)
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test-only-fixture")

    def item(path: Path) -> dict:
        return {"path": path.relative_to(tmp_path).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    now = datetime.now(timezone.utc)
    performed = (now - timedelta(minutes=1)).isoformat()
    actions = {name: True for name in module.DXF_ACTIONS}
    operator = {"id": "engineer-01", "name": "Example Engineer"}
    cad = {
        "product": "AutoCAD", "version": "2018", "operator": operator,
        "performed_at": performed, "actions": actions,
        "input": item(candidate), "output": item(output), "screenshots": [item(screenshot)],
    }
    record = {
        "evidence_kind": "target_cad_edit_save_reopen", "operator": operator,
        "performed_at": performed, "actions": actions, "input": cad["input"], "output": cad["output"],
    }
    record_path.write_text(json.dumps(record), encoding="utf-8")
    cad["evidence_record"] = item(record_path)
    candidate_hashes = {"candidate/input.dxf": item(candidate)["sha256"]}
    for relative in (
        "templates/heater-a4-v1/layout.json",
        "templates/heater-a4-v1/fonts.json",
        "templates/heater-a4-v1/manifest.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"test_only": True}), encoding="utf-8")
    template_sha = hashlib.sha256(
        (tmp_path / "templates/heater-a4-v1/manifest.json").read_bytes()
    ).hexdigest()
    layout_sha = hashlib.sha256(
        (tmp_path / "templates/heater-a4-v1/layout.json").read_bytes()
    ).hexdigest()
    fonts_sha = hashlib.sha256(
        (tmp_path / "templates/heater-a4-v1/fonts.json").read_bytes()
    ).hexdigest()
    face_sha = "f" * 64
    manifest_path = candidate.parent / "candidate-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "template": {
                    "manifest_sha256": template_sha,
                    "layout_sha256": layout_sha,
                    "fonts_sha256": fonts_sha,
                },
                "font": {"font_sha256": face_sha},
            }
        ),
        encoding="utf-8",
    )
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    probe = {
        "candidate_built_at": (now - timedelta(minutes=2)).isoformat(),
        "candidate_manifest_sha256": manifest_sha,
        "validated_candidate_hashes": candidate_hashes,
    }
    approval = {
        "status": "approved", "actor": "engineer-01", "decided_at": now.isoformat(),
        "scope": module.APPROVAL_SCOPE, "conclusion": "approved_for_dxf_pdf_v1",
        "candidate": {
            "path": "candidate",
            "profile": "dxf_pdf_v1",
            "candidate_manifest_sha256": manifest_sha,
            "template_manifest_sha256": template_sha,
            "layout_sha256": layout_sha,
        },
        "font": {
            "profile_sha256": fonts_sha,
            "extracted_face_sha256": face_sha,
        },
        "target_cad": cad, "artifact_hashes": candidate_hashes,
    }
    assert module.validate_approval(approval, probe) == []

    wrong_template = json.loads(json.dumps(approval))
    wrong_template["candidate"]["template_manifest_sha256"] = "0" * 64
    assert any(
        "template manifest binding mismatch" in error
        for error in module.validate_approval(wrong_template, probe)
    )

    missing_regen = json.loads(json.dumps(approval))
    del missing_regen["target_cad"]["actions"]["regen"]
    assert any(
        "action shape" in error
        for error in module.validate_approval(missing_regen, probe)
    )

    unrelated = tmp_path / "cad" / "unrelated.dxf"
    shutil.copyfile(candidate, unrelated)
    hollow = json.loads(json.dumps(approval))
    hollow["target_cad"]["input"] = item(unrelated)
    assert any("exact frozen candidate" in error for error in module.validate_approval(hollow, probe))


def test_real_postpone_decision_does_not_require_dwg_conversion() -> None:
    spec = importlib.util.spec_from_file_location("format_gate_postpone", ROOT / "scripts/check_format_gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    built = "2026-11-07T12:00:00+00:00"
    probe = {"candidate_built_at": built, "candidate_manifest_sha256": "a" * 64}
    decision = {
        "status": "approved", "actor": "named-engineer", "decided_at": "2026-11-07T13:00:00+00:00",
        "scope": module.DECISION_SCOPE, "conclusion": "postpone_dwg_keep_dxf_pdf_v1",
        "core_profile": "dxf_pdf_v1", "candidate_manifest_sha256": "a" * 64,
        "dwg_release_decision": "postpone_keep_dxf_pdf_baseline",
    }
    assert module.validate_decision(decision, probe, {"status": "blocked"}, {}) == []


def test_postpone_decision_survives_candidate_regeneration() -> None:
    spec = importlib.util.spec_from_file_location("format_gate_postpone_rebuild", ROOT / "scripts/check_format_gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    decision = {
        "status": "approved",
        "actor": "project-user",
        "decided_at": "2026-11-08T16:31:01+08:00",
        "scope": module.DECISION_SCOPE,
        "conclusion": "postpone_dwg_keep_dxf_pdf_v1",
        "core_profile": "dxf_pdf_v1",
        "candidate_manifest_sha256": "a" * 64,
        "dwg_release_decision": "postpone_keep_dxf_pdf_baseline",
    }
    probe = {
        "candidate_built_at": "2026-11-08T17:40:11+08:00",
        "candidate_manifest_sha256": "a" * 64,
    }
    assert module.validate_decision(decision, probe, {"status": "blocked"}, {}) == []


def test_future_dwg_decision_and_hollow_required_dwg_evidence_are_rejected() -> None:
    spec = importlib.util.spec_from_file_location("format_gate_decisions", ROOT / "scripts/check_format_gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    built = datetime.now(timezone.utc) - timedelta(minutes=1)
    base = {
        "status": "approved", "actor": "named-engineer", "scope": module.DECISION_SCOPE,
        "core_profile": "dxf_pdf_v1", "candidate_manifest_sha256": "a" * 64,
    }
    probe = {"candidate_built_at": built.isoformat(), "candidate_manifest_sha256": "a" * 64}
    future = {**base, "decided_at": "2099-01-01T00:00:00+00:00", "conclusion": "postpone_dwg_keep_dxf_pdf_v1", "dwg_release_decision": "postpone_keep_dxf_pdf_baseline"}
    assert module.validate_decision(future, probe, {"status": "blocked"}, {})
    required = {**base, "decided_at": datetime.now(timezone.utc).isoformat(), "conclusion": "require_dwg_for_first_release", "dwg_release_decision": "first_release_required"}
    errors = module.validate_decision(required, probe, {"status": "available_verified_evaluation_only"}, {"target_cad": {"dwg_edit_save_reopen": True}})
    assert any("structured target-CAD DWG evidence" in error for error in errors)


def test_wrong_page_pdf_is_rejected_by_semantic_probe() -> None:
    spec = importlib.util.spec_from_file_location("probe_formats_semantic", ROOT / "scripts/probe_formats.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = load_template(ROOT / "templates/heater-a4-v1")
    _, pages = load_sample(ROOT / "fixtures/synthetic/heater_sample.json")
    wrong_pdf = ROOT / "docs/evidence/B02-fix-1/candidate/pages/CX-29-KR05-XM01.pdf"
    if not wrong_pdf.is_file():
        pytest.skip("frozen B02-fix-1 candidate is unavailable")
    with pytest.raises(ValueError, match="does not match DrawingPage"):
        module.validate_pdf_page(wrong_pdf, pages[1], template["layout"])


def test_visible_pdf_probe_rejects_shifted_geometry(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("probe_formats_visible", ROOT / "scripts/probe_formats.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = load_template(ROOT / "templates/heater-a4-v1")
    dxf, page, _ = _sample_dxf(tmp_path)
    font_path = fonts.prepare_runtime_font(template["fonts"], ROOT)
    canonical = tmp_path / "canonical.pdf"
    render_page(dxf, canonical, tmp_path / "canonical.png", float(page.scale.denominator), font_path, template["fonts"])
    assert module.compare_visible_pdf(canonical, canonical)["changed_channels"] == 0

    from pypdf import PdfReader, PdfWriter, Transformation
    writer = PdfWriter()
    writer.append(str(canonical))
    shifted = writer.pages[0]
    shifted.add_transformation(Transformation().translate(tx=100 * 72 / 25.4, ty=0))
    shifted_path = tmp_path / "shifted.pdf"
    with shifted_path.open("wb") as stream:
        writer.write(stream)
    with pytest.raises(ValueError, match="visible geometry differs"):
        module.compare_visible_pdf(shifted_path, canonical)


def test_page_consistency_signature_normalizes_only_float_noise() -> None:
    spec = importlib.util.spec_from_file_location("probe_formats_consistency", ROOT / "scripts/probe_formats.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = {
        "row_id": "Sheet1:3",
        "code": "CX-26-KR05-DLL-01",
        "geometry_mm": {"width": 30.0, "length": 50.0},
        "native_dimensions_mm": {"width": 30.0, "length": 50.0},
        "scale": "1:1",
        "geometry_lead_dimension_box_paper_mm": (63.0, 151.76415416098226, 113.23584583901774, 212.0),
        "complete_content_box_paper_mm": (5.0, 6.0, 205.0, 292.0),
        "text_measurements": [{"box_paper_mm": (10.0, 20.0, 30.0, 40.0)}],
        "controlled_layer_display": {
            "DIMENSION": {"color": 7, "off": False, "frozen": False},
        },
        "dimension_parent_display": {
            "width": {"layer": "DIMENSION", "color": 256, "linetype": "BYLAYER"},
        },
        "dimension_linetype_sources": {
            "width": {
                "dimstyle": "HEATER_DIM",
                "fields": {
                    "dimltype": {
                        "origin": "dimstyle",
                        "source": "omitted_default",
                        "effective_linetype": "Continuous",
                    }
                },
            }
        },
        "dimension_cache_semantics": {
            "width": [{"type": "LINE", "start": [1.0, 2.0, 0.0], "end": [3.0, 4.0, 0.0]}]
        },
        "dimension_text_measurements": {
            "width": {
                "text": "30",
                "style": "HEATER_CJK",
                "cap_height_paper_mm": 3.5,
                "box_paper_mm": [70.0, 140.0, 75.0, 143.5],
            }
        },
    }
    noisy = json.loads(json.dumps(page))
    noisy["geometry_lead_dimension_box_paper_mm"][2] += 3e-14
    assert module.page_consistency_signature(page) == module.page_consistency_signature(noisy)

    shifted = json.loads(json.dumps(page))
    shifted["geometry_lead_dimension_box_paper_mm"][2] += 0.001
    assert module.page_consistency_signature(page) != module.page_consistency_signature(shifted)

    cache_noise = json.loads(json.dumps(page))
    cache_noise["dimension_cache_semantics"]["width"][0]["start"][0] += 3e-14
    assert module.page_consistency_signature(page) == module.page_consistency_signature(cache_noise)

    cache_shift = json.loads(json.dumps(page))
    cache_shift["dimension_cache_semantics"]["width"][0]["start"][0] += 0.001
    assert module.page_consistency_signature(page) != module.page_consistency_signature(cache_shift)

    parent_shift = json.loads(json.dumps(page))
    parent_shift["dimension_parent_display"]["width"]["color"] = 2
    assert module.page_consistency_signature(page) != module.page_consistency_signature(parent_shift)

    source_shift = json.loads(json.dumps(page))
    source_shift["dimension_linetype_sources"]["width"]["fields"]["dimltype"]["source"] = "TEST_DASHED"
    assert module.page_consistency_signature(page) != module.page_consistency_signature(source_shift)

    layer_shift = json.loads(json.dumps(page))
    layer_shift["controlled_layer_display"]["DIMENSION"]["off"] = True
    assert module.page_consistency_signature(page) != module.page_consistency_signature(layer_shift)

    mtext_format_shift = json.loads(json.dumps(page))
    mtext_format_shift["text_measurements"][0]["effective_format"] = [
        {"cap_height": 3.0}
    ]
    assert module.page_consistency_signature(page) != module.page_consistency_signature(
        mtext_format_shift
    )

    dimension_text_shift = json.loads(json.dumps(page))
    dimension_text_shift["dimension_text_measurements"]["width"]["box_paper_mm"][2] += 0.001
    assert module.page_consistency_signature(page) != module.page_consistency_signature(
        dimension_text_shift
    )


def test_dwg_semantic_signature_binds_coordinates_styles_dimensions_and_layout(tmp_path: Path) -> None:
    path, page, _ = _sample_dxf(tmp_path)
    before = dwg_adapter._audited_dxf_signature(path)
    document = ezdxf.readfile(path)
    next(iter(document.modelspace().query("LWPOLYLINE[layer=='HEATER']"))).translate(1, 0, 0)
    document.styles.get("HEATER_CJK").dxf.font = "arial.ttf"
    viewport = next(v for v in document.layouts.get(page.code).query("VIEWPORT") if v.has_xdata("HEATER_DRAWING"))
    viewport.dxf.view_twist_angle = 1
    changed = tmp_path / "changed.dxf"
    document.saveas(changed)
    assert dwg_adapter._audited_dxf_signature(changed) != before
