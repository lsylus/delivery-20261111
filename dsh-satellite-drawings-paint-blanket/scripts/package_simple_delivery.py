"""Package committed sources and current reviewed samples; --check never builds or packs."""
import argparse
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = [
    ".gitattributes", ".gitignore", ".node-version", ".python-version", "README.md",
    "package.json", "package-lock.json", "pyproject.toml", "uv.lock", "tsconfig.json", "tsconfig.b07.json",
    "contracts", "packages", "plugins", "service", "scripts", "tests", "deploy",
    "fixtures/synthetic", "fixtures/contracts", "docs/simple-v1-requirements.md",
    "docs/reports/simple-v1.md", "docs/reports/step-import-comparison.md", "docs/architecture/opencadstudio-output.md",
]
CASES = ("cube", "cylinder", "cube-cylinder")
LOG_NAMES = ("final-python-tests.log", "bridge-tests.log", "final-workflow.log",
             "final-cylinder-height.log", "final-satellite.log", "final-import-regression.log",
             "final-catalog-integration-tests.log", "final-satellite-catalog.log",
             "final-satellite-shared.log", "final-satellite-parallel.log", "final-import-checkpoint-tests.log")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_record(record, expected_root):
    path = Path(record["path"]).resolve()
    path.relative_to(expected_root.resolve())
    if not path.is_file() or path.is_symlink() or sha(path) != record["sha256"]:
        raise ValueError("Missing or stale reviewed artifact: " + str(path))
    return path


def materials():
    evidence = ROOT / "work/simple-v1-evidence/final"
    fixture_root = ROOT / "fixtures/synthetic/simple-v1"
    required = [ROOT / p for p in SOURCE_PATHS]
    required += [ROOT / "plugins/blanket/plugin" / p for p in
                 ("lib/index.mjs", "lib/client.js", "public/app.js", "public/index.html",
                  "public/app.css", "mcp/server.mjs", "cordis.patch.yml")]
    required += [fixture_root / (name + ".step") for name in CASES]
    required += [fixture_root / "manifest.json", evidence / "workflow-summary.json", evidence / "dwg-review.json"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise ValueError("Missing delivery materials: " + ", ".join(missing))
    review = json.loads((evidence / "dwg-review.json").read_text())
    if review.get("status") != "passed_with_display_limitations":
        raise ValueError("Final DWG review is not complete")
    indexed = {case["case"]: case for case in review["cases"]}
    examples = set(fixture_root.iterdir())
    for name in CASES:
        case = indexed[name]
        dwg = checked_record(case["dwg"], evidence)
        png = checked_record(case["original_product_png"], evidence)
        if dwg != evidence / (name + ".dwg") or png != evidence / (name + "-opencad.png"):
            raise ValueError("Review does not bind the expected final filenames: " + name)
        report_path = evidence / (name + "-opencad.preview.json")
        preview = json.loads(report_path.read_text())
        if (not case["source_binding_passed"] or preview["input"]["sha256"] != sha(dwg)
                or preview["preview"]["sha256"] != sha(png)
                or preview["revision_id"] != case["revision_id"]):
            raise ValueError("Final product preview binding mismatch: " + name)
        examples.update((dwg, png, report_path))
        for record in case.get("additional_captures", []):
            capture = checked_record(record, evidence)
            capture_report = capture.with_suffix(".preview.json")
            bound = json.loads(capture_report.read_text())
            if bound["input"]["sha256"] != sha(dwg) or bound["preview"]["sha256"] != sha(capture):
                raise ValueError("Localized capture is stale: " + str(capture))
            examples.update((capture, capture_report))
        workbench = evidence / (name + "-workbench.png")
        if workbench.is_file():
            examples.add(workbench)
    for name in ("piece-limit.png", "piece-limit.json"):
        if (evidence / name).is_file():
            examples.add(evidence / name)
    # Explicit reviewed records above exclude superseded cylinder screenshots.
    supplemental = []
    for name in ("workflow-summary.json", "dwg-review.json", "satellite.json", "satellite-failure.json"):
        if (evidence / name).is_file():
            supplemental.append(evidence / name)
    for name in ("three-profile-original-brep-comparison.json", "def26-native-triangles-versus-active-filters.json", "shared-viewer-result.json"):
        path = ROOT / "work/simple-v1-large-probe" / name
        if path.is_file():
            supplemental.append(path)
    logs = [ROOT / "work/simple-v1-evidence" / name for name in LOG_NAMES
            if (ROOT / "work/simple-v1-evidence" / name).is_file()]
    satellite_path = evidence / "satellite.json"
    satellite_passed = False
    if satellite_path.is_file():
        try:
            satellite_result = json.loads(satellite_path.read_text())
            satellite_passed = isinstance(satellite_result, dict) and satellite_result.get("status") == "passed"
        except (OSError, ValueError):
            # A retry may still be writing the evidence; an incomplete record is not acceptance.
            satellite_passed = False
    changes = subprocess.check_output(["git", "status", "--porcelain", "--", *SOURCE_PATHS],
                                      cwd=ROOT, text=True).splitlines()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return {"head": head, "source_ready_for_archive": not changes,
            "source_change_count": len(changes), "example_file_count": len(examples),
            "supplemental_file_count": len(supplemental), "logs": [p.name for p in logs],
            "review_status": review["status"],
            "satellite_acceptance": "passed" if satellite_passed else "not_completed",
            "examples": sorted(examples), "supplemental": supplemental, "log_paths": logs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate inputs only; no npm, output folder or archive")
    parser.add_argument("--output", type=Path, default=ROOT / "work/simple-v1-delivery")
    args = parser.parse_args()
    material = materials()
    summary = {key: value for key, value in material.items()
               if key not in ("examples", "supplemental", "log_paths")}
    if args.check:
        print(json.dumps({"materials_complete": True, "packing_performed": False, **summary},
                         ensure_ascii=False, indent=2))
        return
    if not material["source_ready_for_archive"]:
        raise RuntimeError("Commit the selected source changes before archiving HEAD; use --check to inspect readiness")
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("Delivery directory must be new; prior packages are preserved: " + str(output))
    output.mkdir(parents=True)
    env = dict(os.environ, PATH=str(ROOT / ".tools/node/bin") + os.pathsep + os.environ.get("PATH", ""))
    packed = subprocess.run(
        ["npm", "pack", "--workspace", "plugins/blanket/plugin", "--pack-destination", str(output), "--json"],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    plugin = json.loads(packed.stdout)[0]
    source = output / "thermal-simple-v1-source.tar.gz"
    subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(source), "HEAD", *SOURCE_PATHS],
                   cwd=ROOT, check=True)
    examples = output / "examples"
    examples.mkdir()
    for file in material["examples"]:
        shutil.copy2(file, examples / file.name)
    for file in material["supplemental"] + material["log_paths"]:
        shutil.copy2(file, output / file.name)
    shutil.copy2(ROOT / "docs/reports/simple-v1.md", output / "使用说明与验证结果.md")
    records = []
    for file in sorted(output.rglob("*")):
        if file.is_file() and file.name != "manifest.json":
            records.append({"path": str(file.relative_to(output)), "bytes": file.stat().st_size, "sha256": sha(file)})
    (output / "manifest.json").write_text(json.dumps(
        {"head": material["head"], "plugin": plugin["filename"], "files": records,
         "satellite_acceptance": material["satellite_acceptance"]},
        ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"directory": str(output), "head": material["head"],
                      "plugin": plugin["filename"], "file_count": len(records)}, indent=2))


if __name__ == "__main__":
    main()
