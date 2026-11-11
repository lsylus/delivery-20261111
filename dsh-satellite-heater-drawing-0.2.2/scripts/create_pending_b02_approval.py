#!/usr/bin/env python3
"""Create the fillable, non-approving B02 human-review record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = (
        (ROOT / args.evidence).resolve()
        if not args.evidence.is_absolute()
        else args.evidence.resolve()
    )
    if not evidence.is_relative_to((ROOT / "docs/evidence").resolve()):
        parser.error("evidence must stay inside docs/evidence")
    candidate = evidence / "candidate"
    manifest = load(candidate / "candidate-manifest.json")
    probe = load(evidence / "validation/probe-result.json")
    contract = load(ROOT / "scripts/b02_approval_contract.json")
    fonts = load(ROOT / "templates/heater-a4-v1/fonts.json")
    layout = load(ROOT / "templates/heater-a4-v1/layout.json")
    candidate_relative = candidate.relative_to(ROOT).as_posix()
    payload = {
        "schema_version": 4,
        "approval_claim": "none",
        "status": "pending",
        "actor": None,
        "role": None,
        "decided_at": None,
        "scope": contract["approval_scope"],
        "conclusion": None,
        "candidate": {
            "path": candidate_relative,
            "profile": "dxf_pdf_v1",
            "candidate_manifest_sha256": sha256(
                candidate / "candidate-manifest.json"
            ),
            "template_manifest_sha256": sha256(
                ROOT / "templates/heater-a4-v1/manifest.json"
            ),
            "layout_sha256": sha256(
                ROOT / "templates/heater-a4-v1/layout.json"
            ),
        },
        "font": {
            "family": fonts["face_family"],
            "postscript": fonts["face_postscript_name"],
            "extracted_face_sha256": manifest["font"]["font_sha256"],
            "profile_sha256": sha256(
                ROOT / "templates/heater-a4-v1/fonts.json"
            ),
        },
        "reconstruction_candidates": {
            "heater_center_paper_mm": layout["heater_center_paper_mm"],
            "lead_parameters_paper_mm": layout["lead_parameters_paper_mm"],
            "dimension_placement_paper_mm": layout[
                "dimension_placement_paper_mm"
            ],
            "engineering_approval": "pending",
        },
        "target_cad": {
            "product": "AutoCAD",
            "version": "2018",
            "operator": None,
            "operator_role": None,
            "performed_at": None,
            "actions": {name: False for name in contract["dxf_actions"]},
            "input": None,
            "output": None,
            "evidence_record": None,
            "screenshots": [],
            "dwg_validation": None,
        },
        "artifact_hashes": probe["validated_candidate_hashes"],
        "required_actions": [
            f"Before manufacturing delivery, a named engineer with a recorded role must inspect the exact {evidence.name} frozen candidate in AutoCAD 2018.",
            "Open the exact hashed input; edit outline, text, and native dimensions; explicitly update dimensions and run REGEN; save, close, and reopen.",
            "Confirm native black/yellow frame display, MTEXT inline/paragraph formatting and flow, glyph cell/frame bounds, HZ font resolution, temporary PDF rendering limits, reconstructed sample placements, fallback policy, units, and controlled dimension regeneration.",
            "Record exact input/output hashes, structured operation facts, operator/time, and PNG/PDF screenshots.",
            "Approve or reject the exact native template mapping, CAD/PDF font treatment, the deterministic short-edge lead rule, collision rejection policy, and measured visual differences.",
        ],
        "note": (
            "Pending human record. Automation, synthetic fixtures, unrelated files, "
            "future-dated records, and this empty template cannot approve it. "
            f"{evidence.name} regeneration invalidates all prior candidate-specific approval."
        ),
    }
    output = evidence / "human-approval.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"path": str(output), "sha256": sha256(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
