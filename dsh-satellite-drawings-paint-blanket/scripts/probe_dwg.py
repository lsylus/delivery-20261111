"""Real B04 probe. Exit 3 means a missing external prerequisite, never success."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile

import ezdxf
import shapely

from thermal_drawings.drawing.document import DrawingDocument
from thermal_drawings.drawing.dxf_export import DrawingExporter
from thermal_drawings.drawing.profiles import DrawingProfile
from thermal_drawings.drawing.converter import DwgConverter, ConversionError
from thermal_drawings.drawing.validation import validate_dxf, file_record
from contracts import validate

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reuse-reviewed", action="store_true", help="revalidate an already reviewed immutable candidate")
    args = parser.parse_args()
    evidence = ROOT / "docs/evidence/B04"
    evidence.mkdir(parents=True, exist_ok=True)
    if args.reuse_reviewed and (evidence / "autocad-reopen.json").exists():
        # AutoCAD review binds bytes. Regenerating DWG would invalidate that review.
        from check_b04_acceptance import assess_evidence
        gate = assess_evidence(ROOT)
        if gate["status"] != "pass":
            print(json.dumps(gate)); return 3
        result = json.loads((evidence / "conversion.json").read_text())
        if result["fixture"]["sha256"] != file_record(args.fixture)["sha256"]:
            print("BLOCKED: reviewed fixture differs from requested input"); return 3
        document = DrawingDocument.read(args.fixture)
        validate_dxf(document, result["input"]["path"])
        validate_dxf(document, result["readback"]["file"]["path"])
        print("Validated existing reviewed DWG bytes, input, implementation and DXF readback; no regeneration")
        return 0
    # Direct probe calls must not leave an old successful candidate looking current.
    for name in ("sample.dwg", "sample.readback.dxf", "capability.json", "conversion.json", "dxf-readback.json"):
        (evidence / name).unlink(missing_ok=True)
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT / "work"):
        raise ValueError("probe output must be in NEW_ROOT/work")
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="probe-", dir=output))

    def save(name, data):
        (evidence / name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")

    profile = DrawingProfile()
    document = DrawingDocument.read(args.fixture)
    dxf = DrawingExporter().write_dxf(document, run / "sample.dxf", profile)
    readback = validate_dxf(document, dxf, profile)
    shutil.copyfile(dxf, evidence / "sample.dxf")
    readback["file"] = file_record(evidence / "sample.dxf")
    save("dxf-readback.json", readback)
    config_path = Path(args.config)
    config_missing = not config_path.is_file()
    config = json.loads((ROOT / "work/config/converters.example.json" if config_missing else config_path).read_text())
    validate("config", config)
    converter = DwgConverter(config["dwg"])
    capability = converter.capabilities()
    capability.update({"platform": platform.platform(), "python": platform.python_version(),
                       "ezdxf": ezdxf.__version__, "shapely": shapely.__version__,
                       "config_missing": config_missing, "target_profile": profile.__dict__,
                       "input": file_record(args.fixture)})
    save("capability.json", capability)
    code = 3
    try:
        result = converter.convert(dxf, run / "sample.dwg", profile, document=document)
        shutil.copyfile(run / "sample.dwg", evidence / "sample.dwg")
        shutil.copyfile(run / "sample.readback.dxf", evidence / "sample.readback.dxf")
        result["output"] = file_record(evidence / "sample.dwg")
        result["readback"]["file"] = file_record(evidence / "sample.readback.dxf")
        capability.update(real_conversion_verified=True, status="verified_evaluation_only" if not result["capability"].get("production_deployment_approved") else "verified_for_this_conversion")
        save("capability.json", capability)
        code = 0
        result["reason"] = "AutoCAD independent edit/save/reopen is still required"
    except ConversionError as exc:
        result = {"status": "blocked" if exc.code in ("capability_unavailable", "font_missing") else "failed",
                  "error_code": exc.code, "reason": str(exc), "evidence": exc.evidence,
                  "commands": converter.commands, "formal_artifact_published": False,
                  "input": file_record(dxf), "output": None, "autocad_reopen": "not_run"}
        code = 3 if result["status"] == "blocked" else 1
    result["revision_id"] = document.to_dict()["revision_id"]
    result["fixture"] = file_record(args.fixture)
    result["implementation"] = [file_record(p) for p in sorted((ROOT / "service/src/thermal_drawings/drawing").glob("*")) if p.suffix in (".py", ".json")]
    result.setdefault("resources_created", []).append(str(run))
    result.setdefault("resources_cleaned", [])  # Retained run evidence, no worker remains alive.
    save("conversion.json", result)
    print(json.dumps({"dxf": readback["status"], "dwg": result["status"], "reason": result["reason"]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
