"""Package the new motor feature workflow; --check never builds, packs or creates outputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from package_simple_delivery import materials as simple_materials, SOURCE_PATHS as SIMPLE_SOURCE_PATHS

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = list(dict.fromkeys(SIMPLE_SOURCE_PATHS + [
    "docs/feature-composite-requirements.md", "docs/reports/feature-composite-v1.md",
    "fixtures/real-derived", "docs/evidence/B13/r4-review/run-01/complete-motor.step",
]))
EVIDENCE = ROOT / "work/feature-composite-evidence"
FEATURE_SOURCE_PATHS = [
    "package-lock.json", "plugins/blanket/plugin/package.json",
    "plugins/blanket/web/src/BlanketWorkbench.tsx",
    "service/src/thermal_drawings/blanket/feature_cover.py",
    "service/src/thermal_drawings/blanket/overlaps.py",
    "service/src/thermal_drawings/blanket/seam_plans.py",
    "tests/blanket/test_feature_cover.py",
    "scripts/check_feature_workflow.mjs", "scripts/package_feature_delivery.py",
    "docs/reports/feature-composite-v1.md",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def checked_record(record, allowed):
    path = Path(record["path"])
    if not path.is_absolute():
        path = ROOT / path
    if path.is_symlink():
        raise ValueError("Symlink evidence is not accepted: " + str(path))
    path = path.resolve()
    if not any(path.is_relative_to(base.resolve()) for base in allowed):
        raise ValueError("Evidence is outside the selected roots: " + str(path))
    if not path.is_file() or record.get("sha256") != sha(path):
        raise ValueError("Missing or stale evidence: " + str(path))
    return path


def load_net(path):
    value = read_json(path)
    for candidate in (value, value.get("net", {}), value.get("net", {}).get("net", {})):
        if "drawing_document" in candidate and "fixed_points" in candidate:
            return candidate
    raise ValueError("Expected actual NetResult: " + str(path))


def collect(args):
    old = simple_materials()  # reviewed old samples are appendices, never new acceptance
    workflow_path, audit_path = args.workflow.resolve(), args.audit.resolve()
    workflow, audit = read_json(workflow_path), read_json(audit_path)
    if workflow.get("status") != "passed" or workflow.get("policy") != "feature_composite_v1":
        raise ValueError("New motor UI workflow has not passed feature_composite_v1")
    if audit.get("status") != "passed" or not audit.get("moved_point", {}).get("cut_geometry_unchanged"):
        raise ValueError("New before/after native DWG and marker audit has not passed")
    cover_path = args.cover.resolve()
    cover = read_json(cover_path)["blanket"]
    identity = cover["baseline"]["parameters"]["identity"]
    if identity.get("construction_version") != "native-serial-feature-union-v1":
        raise ValueError("Motor cover is not from the frozen native serial construction")
    source = checked_record(workflow["source"], [ROOT / "docs/evidence", ROOT / "fixtures"])
    if source.suffix.lower() not in (".step", ".stp"):
        raise ValueError("Motor source must be the actual STEP sample")
    files = {workflow_path, audit_path, cover_path, source}
    evidence = workflow_path.parent
    for name in ("blanket-regression.log", "contracts-formats.log",
                 "feature-focused.log", "frontend-build.log"):
        log = evidence / name
        if not log.is_file():
            raise ValueError("Missing final feature regression log: " + name)
        files.add(log)
    allowed = [EVIDENCE, workflow_path.parent, audit_path.parent]
    revisions = {}
    for label in ("before", "after"):
        native = audit[label]
        dwg = checked_record(native["dwg"], allowed)
        net = checked_record(native["source_net"], allowed)
        ui_dwg = checked_record(workflow["exports"][label], allowed)
        if ui_dwg != dwg or dwg.read_bytes()[:6] != b"AC1032":
            raise ValueError("UI workflow and native audit must bind identical DWG2018 bytes")
        value = load_net(net)
        if value["cover_baseline_id"] != cover["baseline"]["id"] or value["model_ref"] != cover["model_ref"]:
            raise ValueError("Audited NetResult does not belong to the frozen cover baseline")
        features = value.get("feature_composite", {}).get("features", [])
        if len(features) < 2 or {f["kind"] for f in features} != {"box", "cylinder"}:
            raise ValueError("Motor evidence must contain the new mixed native feature composite")
        selected_ref = workflow["selection"]["target_click"]["ref"]
        if any(value["model_ref"].get(key) != selected_ref[key]
               for key in ("project_id", "model_id", "model_revision", "assembly_digest")):
            raise ValueError("Motor NetResult is not bound to this UI imported model")
        if value["revision_id"] != native["revision_id"]:
            raise ValueError("Audited NetResult revision changed")
        if native.get("status") != "passed" or native.get("piece_limit_exceeded"):
            raise ValueError("Native feature manufacturing or explicit piece limit remains unmet")
        if native["actual_piece_count_per_layer"] != len(value["pieces"]):
            raise ValueError("Actual cutting piece count does not match NetResult")
        revisions[label] = {"revision_id": value["revision_id"], "dwg_sha256": sha(dwg),
                            "net_sha256": sha(net), "actual_piece_count_per_layer": len(value["pieces"]),
                            "net_status": value.get("status"),
                            "manufacturing_summary": value.get("manufacturing_summary", {}),
                            "interface_pattern_status": value["feature_composite"].get("interface_pattern_status"),
                            "installation_opening": value["feature_composite"].get("installation_opening", False),
                            "bottom_fixed": value["feature_composite"].get("bottom_fixed", False)}
        files.update((dwg, net))
    point_id = workflow.get("point_id", workflow.get("moved_point", {}).get("point_id"))
    if point_id != audit["moved_point"]["point_id"]:
        raise ValueError("UI and native audit do not identify the same persistent point")
    # Restored state is separately saved by the real UI script, not manufactured here.
    restored = args.restored_net.resolve()
    restored_net = load_net(restored)
    after_point = audit["moved_point"]["after"]
    restored_point = next(p for p in restored_net["fixed_points"] if p["id"] == point_id)
    if restored_point["uv_mm"] != after_point["panel_uv_mm"] or restored_point["panel_key"] != after_point["panel_key"]:
        raise ValueError("Restored UI state did not retain the moved point")
    files.add(restored)
    for record in workflow.get("artifacts", []):
        files.add(checked_record(record, allowed))
    for label in ("before", "after"):
        for suffix in (".readback.dxf", ".validated.dxf"):
            path = audit_path.parent / (label + suffix)
            if path.is_file():
                files.add(path)
    # Publication renames staging atomically. Preserve the native report bytes;
    # resolve its original filenames beside the published report and verify hashes.
    preview_bindings = []
    for preview_report in args.preview_report:
        preview_report = preview_report.resolve()
        preview = read_json(preview_report)
        def published_record(record):
            candidate = preview_report.parent / Path(record["path"]).name
            return checked_record({**record, "path": str(candidate)}, [preview_report.parent])
        dwg = published_record(preview["input"])
        png = published_record(preview["preview"])
        if (not preview.get("ok") or preview.get("missing_fonts")
                or preview.get("revision_id") != revisions["after"]["revision_id"]
                or sha(dwg) != revisions["after"]["dwg_sha256"]):
            raise ValueError("Native GUI capture does not show the final after DWG")
        files.update((preview_report, png, dwg))
        preview_bindings.append({"report_sha256": sha(preview_report), "published_report_path": str(preview_report),
                                 "dwg_sha256": sha(dwg), "png_sha256": sha(png),
                                 "published_png_path": str(png), "revision_id": preview["revision_id"],
                                 "path_resolution": "original staging filenames resolved in the same published directory; hashes unchanged"})
    supplemental = []
    for extra_path in args.supplemental_workflow:
        extra_path = extra_path.resolve()
        extra = read_json(extra_path)
        if extra.get("status") != "passed" or extra.get("policy") != "feature_composite_v1":
            raise ValueError("Supplemental feature workflow has not passed: " + str(extra_path))
        extra_source = checked_record(extra["source"], [ROOT / "docs/evidence", ROOT / "fixtures"])
        files.update((extra_path, extra_source))
        for label, record in extra["exports"].items():
            dwg = checked_record(record, [extra_path.parent])
            if dwg.read_bytes()[:6] != b"AC1032":
                raise ValueError("Supplemental export is not actual DWG2018 bytes")
            files.add(dwg)
        for record in extra.get("artifacts", []):
            files.add(checked_record(record, [extra_path.parent]))
        extra_audit_path = extra_path.parent / "native-audit/native-dwg-audit.json"
        audit_acceptance = "not_run"
        if extra_audit_path.is_file():
            extra_audit = read_json(extra_audit_path)
            if extra_audit.get("status") != "passed":
                raise ValueError("Supplemental native audit failed")
            for label in ("before", "after"):
                if label in extra_audit:
                    dwg = checked_record(extra_audit[label]["dwg"], [extra_path.parent])
                    net = checked_record(extra_audit[label]["source_net"], [extra_path.parent])
                    if sha(dwg) not in {record["sha256"] for record in extra["exports"].values()}:
                        raise ValueError("Supplemental native audit binds a different DWG")
                    files.update((dwg, net))
            files.add(extra_audit_path)
            for name in ("before.readback.dxf", "before.validated.dxf", "after.readback.dxf", "after.validated.dxf"):
                path = extra_audit_path.parent / name
                if path.is_file():
                    files.add(path)
            audit_acceptance = "passed"
        supplemental.append({"case": extra.get("case", extra_path.parent.name),
                             "workflow_sha256": sha(extra_path), "source_sha256": sha(extra_source),
                             "workflow_acceptance": "editable_draft_workflow_passed",
                             "native_dwg_audit_acceptance": audit_acceptance,
                             "complete_manufacturing_acceptance": "not_completed"})
    for path in files:
        if not path.is_relative_to(ROOT) or not path.is_file() or path.is_symlink():
            raise ValueError("Delivery evidence must be a regular repository-local file")
    changes = subprocess.check_output(["git", "status", "--porcelain", "--", *FEATURE_SOURCE_PATHS], cwd=ROOT, text=True).splitlines()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return {"old": old, "files": sorted(files), "head": head,
            "plugin_version": read_json(ROOT / "plugins/blanket/plugin/package.json")["version"],
            "frozen_construction_version": "native-serial-feature-union-v1",
            "source_ready_for_archive": not changes, "source_change_count": len(changes),
            "feature_acceptance": "native_drawing_editable_draft_workflow_passed",
            "complete_manufacturing_acceptance": "not_completed",
            "delivery_scope": "Editable native drawing draft with planar fold merging and segmented circular fan-tab candidates; material behaviour requires samples; the selected plane is a positioning reference only",
            "motor_source_sha256": sha(source),
            "workflow_sha256": sha(workflow_path), "native_audit_sha256": sha(audit_path),
            "point_id": point_id, "revisions": revisions, "preview_bindings": preview_bindings,
            "supplemental_workflows": supplemental,
            "satellite_acceptance": old["satellite_acceptance"],
            "satellite_15_minute_target": "paused_not_a_packaging_gate"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate only; no npm, build, archive or output folder")
    parser.add_argument("--workflow", type=Path, default=EVIDENCE / "workflow.json")
    parser.add_argument("--cover", type=Path, default=EVIDENCE / "motor-cover.json")
    parser.add_argument("--audit", type=Path, default=EVIDENCE / "native-audit/native-dwg-audit.json")
    parser.add_argument("--restored-net", type=Path, default=EVIDENCE / "motor-restored-net.json")
    parser.add_argument("--preview-report", type=Path, action="append", default=[])
    parser.add_argument("--supplemental-workflow", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, default=ROOT / "work/feature-composite-v1-delivery")
    args = parser.parse_args()
    try:
        material = collect(args)
    except (OSError, ValueError, KeyError, StopIteration) as error:
        if not args.check:
            raise
        print(json.dumps({"materials_complete": False, "packing_performed": False,
                          "error": str(error)}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    summary = {k:v for k,v in material.items() if k not in ("old", "files")}
    if args.check:
        print(json.dumps({"materials_complete": True, "packing_performed": False,
                          "feature_evidence_file_count": len(material["files"]), **summary}, ensure_ascii=False, indent=2))
        return
    if not material["source_ready_for_archive"]:
        raise RuntimeError("Commit selected source changes before git archive HEAD; use --check first")
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("Delivery directory must be new; previous packages are preserved")
    output.mkdir(parents=True)
    env = dict(os.environ, PATH=str(ROOT / ".tools/node/bin") + os.pathsep + os.environ.get("PATH", ""))
    packed = subprocess.run(["npm", "pack", "--workspace", "plugins/blanket/plugin", "--pack-destination", str(output), "--json"],
                            cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    plugin = json.loads(packed.stdout)[0]
    subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(output / "thermal-feature-composite-v1-source.tar.gz"), "HEAD", *SOURCE_PATHS], cwd=ROOT, check=True)
    # Preserve original paths and separate new acceptance from the old appendix.
    for path in material["files"]:
        target = output / "feature-evidence" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for path in material["old"]["examples"] + material["old"]["supplemental"] + material["old"]["log_paths"]:
        target = output / "simple-v1-appendix" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    shutil.copy2(ROOT / "docs/reports/feature-composite-v1.md", output / "使用说明与验证结果.md")
    records = [{"path": str(p.relative_to(output)), "bytes": p.stat().st_size, "sha256": sha(p)}
               for p in sorted(output.rglob("*")) if p.is_file() and p != output / "manifest.json"]
    (output / "manifest.json").write_text(json.dumps({**summary, "plugin": plugin["filename"], "files": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"directory": str(output), "plugin": plugin["filename"], "file_count": len(records), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
