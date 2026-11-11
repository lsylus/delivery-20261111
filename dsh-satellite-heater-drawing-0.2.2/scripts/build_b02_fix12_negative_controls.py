#!/usr/bin/env python3
"""Build hash-bound B02 fix-12 MTEXT negative-control evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

import ezdxf

from heater_drawing.domain.models import DrawingPage
from heater_drawing.drawing.fonts import prepare_runtime_font
from heater_drawing.drawing.pdf_renderer import RenderError, merge_pdfs, render_page
from heater_drawing.drawing.template import load_template


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/B02-fix-12"
FROZEN = EVIDENCE / "candidate"
OUTPUT = EVIDENCE / "negative-controls-run-2"
FIXTURE = ROOT / "fixtures/synthetic/heater_sample.json"

CONTROLS = {
    "mtext-h3": {"inline": r"\H3x;", "expected": "MTEXT effective format drift"},
    "mtext-w3": {"inline": r"\W3;", "expected": "MTEXT effective format drift"},
    "mtext-c1": {"inline": r"\C1;", "expected": "MTEXT effective format drift"},
    "flow-direction-3": {"flow_direction": 3, "expected": "MTEXT layout drift"},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def identity(entity) -> tuple[str, ...]:
    try:
        return tuple(
            str(value)
            for code, value in entity.get_xdata("HEATER_DRAWING")
            if code == 1000
        )
    except ezdxf.DXFValueError:
        return ()


def mutate(path: Path, row_id: str, control: dict) -> dict:
    document = ezdxf.readfile(path)
    matches = [
        entity
        for entity in document.modelspace().query("MTEXT")
        if identity(entity) == (row_id, "field", "organization")
    ]
    if len(matches) != 1:
        raise ValueError(f"controlled MTEXT identity mismatch: {path}")
    entity = matches[0]
    before = {
        "raw_text": entity.text,
        "flow_direction": int(entity.dxf.get("flow_direction", 1)),
    }
    if "inline" in control:
        entity.text = "{" + str(control["inline"]) + entity.text + "}"
    else:
        entity.dxf.flow_direction = int(control["flow_direction"])
    after = {
        "raw_text": entity.text,
        "flow_direction": int(entity.dxf.get("flow_direction", 1)),
    }
    document.saveas(path)
    return {"path": path.relative_to(ROOT).as_posix(), "before": before, "after": after}


def refresh_manifest(candidate: Path, control_name: str, control: dict) -> Path:
    path = candidate / "candidate-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    frozen_relative = FROZEN.relative_to(ROOT)
    artifacts = {}
    for old_name in manifest["artifact_hashes"]:
        old_relative = Path(old_name).relative_to(frozen_relative)
        artifact = candidate / old_relative
        artifacts[artifact.relative_to(ROOT).as_posix()] = sha256(artifact)
    manifest["candidate_id"] = candidate.relative_to(ROOT).as_posix()
    manifest["built_at"] = datetime.now(timezone.utc).isoformat()
    manifest["negative_control"] = {
        "name": control_name,
        "mutation": control,
        "expected_probe_failure": control["expected"],
        "source_candidate_manifest_sha256": sha256(
            FROZEN / "candidate-manifest.json"
        ),
    }
    manifest["baseline_pages"] = manifest.pop("pages")
    manifest["artifact_hashes"] = artifacts
    write_json(path, manifest)
    return path


def main() -> int:
    if not FROZEN.is_dir() or not (FROZEN / "candidate-manifest.json").is_file():
        raise ValueError("frozen B02 fix-12 candidate is missing")
    if OUTPUT.exists():
        raise ValueError("negative-control output already exists")
    template = load_template(ROOT / "templates/heater-a4-v1")
    font_path = prepare_runtime_font(template["fonts"], ROOT)
    pages = [
        DrawingPage.model_validate(item)
        for item in json.loads(
            (FROZEN / "drawing-pages.json").read_text(encoding="utf-8")
        )
    ]
    target = pages[0]
    results = []
    ezdxf.options.write_fixed_meta_data_for_testing = True
    for name, control in CONTROLS.items():
        root = OUTPUT / name
        candidate = root / "candidate"
        shutil.copytree(FROZEN, candidate)
        mutations = [
            mutate(candidate / "heater-sample.dxf", target.row_id, control),
            mutate(candidate / "pages" / f"{target.code}.dxf", target.row_id, control),
        ]
        renderer_status = "product_rerender_passed"
        renderer_error = None
        try:
            render_page(
                candidate / "pages" / f"{target.code}.dxf",
                candidate / "pages" / f"{target.code}.pdf",
                candidate / "renders" / f"{target.code}.png",
                float(target.scale.denominator),
                font_path,
                template["fonts"],
            )
        except RenderError as exc:
            if name != "mtext-c1":
                raise
            renderer_status = "product_rerender_rejected_aci_1"
            renderer_error = str(exc)
            (root / "product-renderer.stderr.log").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
            shutil.copy2(
                FROZEN / "pages" / f"{target.code}.pdf",
                candidate / "pages" / f"{target.code}.pdf",
            )
            shutil.copy2(
                FROZEN / "renders" / f"{target.code}.png",
                candidate / "renders" / f"{target.code}.png",
            )
        else:
            (root / "product-renderer.stderr.log").write_text("", encoding="utf-8")
        merge_pdfs(
            [candidate / "pages" / f"{page.code}.pdf" for page in pages],
            candidate / "heater-sample.pdf",
        )
        manifest = refresh_manifest(candidate, name, control)
        validation = root / "validation"
        command = [
            sys.executable,
            str(ROOT / "scripts/probe_formats.py"),
            "--fixture",
            str(FIXTURE),
            "--candidate",
            str(candidate),
            "--profile",
            "dxf_pdf_v1",
            "--output",
            str(validation),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        (root / "probe.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (root / "probe.stderr.log").write_text(completed.stderr, encoding="utf-8")
        expected = str(control["expected"])
        combined_log = completed.stdout + completed.stderr
        if completed.returncode == 0 or expected not in combined_log:
            raise ValueError(
                f"negative control did not fail as expected: {name}: {completed.returncode}"
            )
        result = {
            "name": name,
            "status": "expected_failure_observed",
            "expected_error": expected,
            "probe_exit_code": completed.returncode,
            "command": command,
            "product_renderer_status": renderer_status,
            "product_renderer_error": renderer_error,
            "visual_artifact_policy": (
                "original frozen PDF/PNG copied and rebound because the product renderer "
                "rejected ACI 1 before producing a new visual artifact"
                if renderer_error
                else "mutated DXF successfully rerendered by the product renderer"
            ),
            "mutations": mutations,
            "candidate_manifest_sha256": sha256(manifest),
            "rerendered_pdf_sha256": sha256(
                candidate / "pages" / f"{target.code}.pdf"
            ),
            "rerendered_png_sha256": sha256(
                candidate / "renders" / f"{target.code}.png"
            ),
            "rerendered_merged_pdf_sha256": sha256(
                candidate / "heater-sample.pdf"
            ),
            "stdout_sha256": sha256(root / "probe.stdout.log"),
            "stderr_sha256": sha256(root / "probe.stderr.log"),
        }
        write_json(root / "result.json", result)
        results.append(result)
    summary = {
        "schema_version": 1,
        "source_candidate": FROZEN.relative_to(ROOT).as_posix(),
        "source_candidate_manifest_sha256": sha256(
            FROZEN / "candidate-manifest.json"
        ),
        "prior_attempts_preserved": [
            "docs/evidence/B02-fix-12/negative-controls-incomplete-attempt",
            "docs/evidence/B02-fix-12/negative-controls-diagnostic-palette-aborted",
        ],
        "controls": results,
    }
    write_json(OUTPUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
