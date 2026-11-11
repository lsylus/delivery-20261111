"""Require fresh converted bytes and independent AutoCAD edit/save/reopen evidence."""
import json
from pathlib import Path

from verify_batch import safe, sha

ROOT = Path(__file__).resolve().parents[1]


def assess_evidence(root):
    folder = root / "docs/evidence/B04"
    blockers = []
    try:
        result = json.loads((folder / "conversion.json").read_text())
        if result["status"] != "needs_review" or result.get("output") is None:
            raise ValueError("no real DWG conversion result")
        if len(result["commands"]) != 2 or any(c["exit_code"] or c["timed_out"] for c in result["commands"]):
            raise ValueError("missing successful forward and reverse external command records")
        for record in (result["input"], result["output"], result["readback"]["file"], result["fixture"]):
            path = safe(root, record["path"])
            if sha(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
                raise ValueError("conversion evidence hash mismatch")
        if not result.get("implementation"):
            raise ValueError("missing conversion implementation hashes")
        for record in result["implementation"]:
            if sha(safe(root, record["path"])) != record["sha256"]:
                raise ValueError("conversion implementation changed; review is stale")
        if (folder / "sample.dwg").read_bytes()[:6] != b"AC1032" or result["readback"]["status"] != "pass":
            raise ValueError("DWG header/readback not verified")
        review = json.loads((folder / "autocad-reopen.json").read_text())
        if (review.get("decision") != "approved" or not review.get("reviewer")
                or review.get("software") != "AutoCAD" or not review.get("software_version")
                or not review.get("reviewed_at") or not review.get("license_evidence_ref")
                or review.get("revision_id") != result["revision_id"]
                or review.get("input_dwg_sha256") != result["output"]["sha256"]):
            raise ValueError("named licensed AutoCAD review must bind the exact DWG and revision")
        steps = ("open", "holes_unfilled", "chinese_readable", "mm_scale", "linetypes", "editable_entities",
                 "edit_contour", "edit_dimension", "save", "reopen_edited")
        if any(review.get("checks", {}).get(step) is not True for step in steps):
            raise ValueError("AutoCAD checklist incomplete")
        edited = review["edited_dwg"]
        path = safe(root, edited["path"])
        if sha(path) != edited["sha256"] or edited["sha256"] == result["output"]["sha256"] or path.read_bytes()[:6] != b"AC1032":
            raise ValueError("missing independently saved edited DWG")
        if not review.get("evidence_refs"):
            raise ValueError("missing operation evidence")
        for record in review["evidence_refs"]:
            if sha(safe(root, record["path"])) != record["sha256"]:
                raise ValueError("AutoCAD evidence digest mismatch")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        blockers.append(str(exc))
    return {"status": "blocked" if blockers else "pass", "blockers": blockers,
            "scope": "real Linux DWG conversion plus independent AutoCAD edit/save/reopen"}


if __name__ == "__main__":
    result = assess_evidence(ROOT)
    (ROOT / "docs/evidence/B04/acceptance.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))
    raise SystemExit(3 if result["status"] == "blocked" else 0)
