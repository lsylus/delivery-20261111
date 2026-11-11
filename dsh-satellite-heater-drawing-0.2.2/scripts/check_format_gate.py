#!/usr/bin/env python3
"""Strict machine-readable B02 technical, human, and DWG decision gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parents[1]
APPROVAL_CONTRACT = json.loads(
    (Path(__file__).with_name("b02_approval_contract.json")).read_text(
        encoding="utf-8"
    )
)
APPROVAL_SCOPE = APPROVAL_CONTRACT["approval_scope"]
DXF_ACTIONS = set(APPROVAL_CONTRACT["dxf_actions"])
DWG_ACTIONS = set(APPROVAL_CONTRACT["dwg_actions"])
DECISION_SCOPE = "B02 first-release DWG scope"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def _is_test_identity(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    lowered = value.strip().lower()
    return "synthetic" in lowered or lowered.startswith("test") or "fixture" in lowered


def exact_hashes(expected: dict[str, str]) -> bool:
    for name, digest in expected.items():
        path = ROOT / name
        if not path.is_file() or sha256(path) != digest:
            return False
    return True


def _artifact(item: object) -> tuple[Path, str] | None:
    if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
        return None
    path = ROOT / item["path"]
    if not path.is_file() or sha256(path) != item["sha256"]:
        return None
    return path, item["sha256"]


def _candidate_artifacts(probe: dict) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for name, digest in probe.get("validated_candidate_hashes", {}).items():
        if isinstance(name, str) and isinstance(digest, str):
            result[(ROOT / name).resolve()] = digest
    return result


def _valid_screenshot(item: object) -> bool:
    artifact = _artifact(item)
    if artifact is None:
        return False
    path = artifact[0]
    data = path.read_bytes()
    return (path.suffix.lower() == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or (
        path.suffix.lower() == ".pdf" and data.startswith(b"%PDF-")
    )


def _validate_dwg_cad_record(cad: dict, dwg: dict) -> list[str]:
    errors: list[str] = []
    evidence = cad.get("dwg_validation")
    if not isinstance(evidence, dict):
        return ["required DWG lacks structured target-CAD DWG evidence"]
    actions = evidence.get("actions")
    if not isinstance(actions, dict) or set(actions) != DWG_ACTIONS or not all(actions.values()):
        errors.append("required DWG target-CAD action record is incomplete")
    source = _artifact(evidence.get("input"))
    output = _artifact(evidence.get("output"))
    capability = dwg.get("capability", {})
    verified_dwg = capability.get("verified_dwg") if isinstance(capability, dict) else None
    if evidence.get("input") != verified_dwg:
        errors.append("required DWG target-CAD input is not the exact verified converter output")
    if source is None or source[0].suffix.lower() != ".dwg" or source[0].stat().st_size < 1024 or not source[0].read_bytes().startswith(b"AC1032"):
        errors.append("required DWG target-CAD input is not a substantive ACAD2018 DWG")
    if output is None or output[0].suffix.lower() != ".dwg" or output[0].stat().st_size < 1024 or not output[0].read_bytes().startswith(b"AC1032") or (source and output[0] == source[0]):
        errors.append("required DWG target-CAD saved/reopened output is invalid")
    record_artifact = _artifact(evidence.get("evidence_record"))
    if record_artifact is None or record_artifact[0].suffix.lower() != ".json":
        errors.append("required DWG target-CAD evidence record is missing")
    else:
        record = load(record_artifact[0])
        operator = evidence.get("operator")
        performed = parse_time(evidence.get("performed_at"))
        now = datetime.now(timezone.utc)
        if not isinstance(operator, dict) or any(_is_test_identity(operator.get(key)) for key in ("id", "name")):
            errors.append("required DWG target-CAD named operator is missing or test-only")
        if performed is None or performed > now + timedelta(minutes=5) or performed < now - timedelta(days=30):
            errors.append("required DWG target-CAD operation time is invalid or stale")
        if evidence.get("product") != "AutoCAD" or evidence.get("version") != "2018":
            errors.append("required DWG target-CAD product/version is invalid")
        if (
            record.get("evidence_kind") != "target_cad_dwg_edit_save_reopen"
            or record.get("operator") != operator
            or record.get("performed_at") != evidence.get("performed_at")
            or record.get("product") != evidence.get("product")
            or record.get("version") != evidence.get("version")
            or record.get("actions") != actions
            or record.get("input") != evidence.get("input")
            or record.get("output") != evidence.get("output")
        ):
            errors.append("required DWG target-CAD evidence record does not bind the operation")
    screenshots = evidence.get("screenshots")
    if not isinstance(screenshots, list) or not screenshots or not all(_valid_screenshot(item) for item in screenshots):
        errors.append("required DWG target-CAD screenshots are missing or invalid")
    return errors


def _validate_approval_contract(approval: dict, probe: dict) -> list[str]:
    errors: list[str] = []
    if approval.get("scope") != APPROVAL_SCOPE:
        errors.append("approval scope does not exactly match the B02 approval contract")
    cad = approval.get("target_cad")
    actions = cad.get("actions") if isinstance(cad, dict) else None
    if not isinstance(actions, dict) or set(actions) != DXF_ACTIONS:
        errors.append("target CAD action shape does not exactly match the B02 approval contract")

    candidate = approval.get("candidate")
    if not isinstance(candidate, dict):
        return errors + ["approval candidate binding is missing"]
    candidate_path = candidate.get("path")
    if not isinstance(candidate_path, str):
        return errors + ["approval candidate path is missing"]
    manifest_path = ROOT / candidate_path / "candidate-manifest.json"
    if not manifest_path.is_file():
        return errors + ["approval candidate manifest is missing"]
    manifest_sha = sha256(manifest_path)
    try:
        manifest = load(manifest_path)
    except (OSError, json.JSONDecodeError):
        return errors + ["approval candidate manifest is invalid"]
    template = manifest.get("template", {})
    template_manifest_path = ROOT / "templates/heater-a4-v1/manifest.json"
    layout_path = ROOT / "templates/heater-a4-v1/layout.json"
    fonts_path = ROOT / "templates/heater-a4-v1/fonts.json"
    expected_template_sha = (
        sha256(template_manifest_path) if template_manifest_path.is_file() else None
    )
    expected_layout_sha = sha256(layout_path) if layout_path.is_file() else None
    expected_fonts_sha = sha256(fonts_path) if fonts_path.is_file() else None
    if (
        candidate.get("profile") != "dxf_pdf_v1"
        or candidate.get("candidate_manifest_sha256") != manifest_sha
        or probe.get("candidate_manifest_sha256") != manifest_sha
    ):
        errors.append("approval candidate manifest/profile binding mismatch")
    if (
        candidate.get("template_manifest_sha256") != expected_template_sha
        or template.get("manifest_sha256") != expected_template_sha
    ):
        errors.append("approval template manifest binding mismatch")
    if (
        candidate.get("layout_sha256") != expected_layout_sha
        or template.get("layout_sha256") != expected_layout_sha
    ):
        errors.append("approval layout binding mismatch")
    font = approval.get("font")
    if (
        not isinstance(font, dict)
        or font.get("profile_sha256") != expected_fonts_sha
        or template.get("fonts_sha256") != expected_fonts_sha
        or font.get("extracted_face_sha256") != manifest.get("font", {}).get("font_sha256")
    ):
        errors.append("approval font binding mismatch")
    return errors


def validate_approval(approval: dict, probe: dict) -> list[str]:
    errors = _validate_approval_contract(approval, probe)
    if approval.get("status") != "approved":
        return errors + ["template/font/lead/target-CAD approval is pending"]
    actor = approval.get("actor")
    if _is_test_identity(actor) or approval.get("test_only") is True:
        errors.append("approval actor is missing or test-only")
    decided = parse_time(approval.get("decided_at"))
    built = parse_time(probe.get("candidate_built_at"))
    now = datetime.now(timezone.utc)
    if decided is None or decided > now + timedelta(minutes=5) or decided < now - timedelta(days=30):
        errors.append("approval decision time is invalid or stale")
    if built is None or decided is None or decided < built:
        errors.append("approval predates candidate generation/validation")
    if approval.get("conclusion") != "approved_for_dxf_pdf_v1":
        errors.append("approval scope/conclusion does not exactly match B02")
    cad = approval.get("target_cad")
    if not isinstance(cad, dict) or cad.get("product") != "AutoCAD" or cad.get("version") != "2018":
        errors.append("AutoCAD 2018 edit-save-reopen evidence is missing")
    else:
        operator = cad.get("operator")
        performed = parse_time(cad.get("performed_at"))
        if not isinstance(operator, dict) or any(_is_test_identity(operator.get(key)) for key in ("id", "name")):
            errors.append("target CAD named operator is missing or test-only")
        if performed is None or built is None or performed < built or performed > now + timedelta(minutes=5) or performed < now - timedelta(days=30):
            errors.append("target CAD operation time is invalid or stale")
        actions = cad.get("actions")
        if not isinstance(actions, dict) or set(actions) != DXF_ACTIONS or not all(actions.values()):
            errors.append("target CAD edit/update/save/reopen action record is incomplete")
        input_artifact = _artifact(cad.get("input"))
        output_artifact = _artifact(cad.get("output"))
        expected_artifacts = _candidate_artifacts(probe)
        if input_artifact is None or expected_artifacts.get(input_artifact[0].resolve()) != input_artifact[1] or input_artifact[0].suffix.lower() != ".dxf":
            errors.append("target CAD input is not an exact frozen candidate DXF")
        if output_artifact is None or output_artifact[0].suffix.lower() != ".dxf" or (input_artifact and output_artifact[0] == input_artifact[0]):
            errors.append("target CAD saved/reopened DXF output is missing")
        elif output_artifact:
            try:
                document = ezdxf.readfile(output_artifact[0])
                if document.audit().has_errors:
                    raise ValueError("audit errors")
            except (OSError, ValueError, ezdxf.DXFError):
                errors.append("target CAD output is not a valid audited DXF")
        record_artifact = _artifact(cad.get("evidence_record"))
        screenshots = cad.get("screenshots")
        if record_artifact is None or record_artifact[0].suffix.lower() != ".json":
            errors.append("target CAD structured evidence record is missing")
        else:
            record = load(record_artifact[0])
            if record.get("evidence_kind") != "target_cad_edit_save_reopen" or record.get("operator") != operator or record.get("performed_at") != cad.get("performed_at") or record.get("actions") != actions or record.get("input") != cad.get("input") or record.get("output") != cad.get("output"):
                errors.append("target CAD evidence record does not bind the approval facts")
        if not isinstance(screenshots, list) or not screenshots or not all(_valid_screenshot(item) for item in screenshots):
            errors.append("target CAD screenshots are missing or invalid")
    expected_hashes = probe.get("validated_candidate_hashes")
    if approval.get("artifact_hashes") != expected_hashes or not isinstance(expected_hashes, dict) or not exact_hashes(expected_hashes):
        errors.append("approval does not bind every exact existing candidate byte")
    return errors


def validate_decision(decision: dict, probe: dict, dwg: dict, approval: dict) -> list[str]:
    errors = []
    if decision.get("status") != "approved":
        return ["new-evidence DWG release decision is pending"]
    actor = decision.get("actor")
    if _is_test_identity(actor) or decision.get("test_only") is True:
        errors.append("DWG decision actor is missing or test-only")
    decided = parse_time(decision.get("decided_at"))
    probe_time = parse_time(probe.get("candidate_built_at"))
    now = datetime.now(timezone.utc)
    if decided is None or decided > now + timedelta(minutes=5) or decided < now - timedelta(days=30):
        errors.append("DWG decision time is invalid or stale")
    if decision.get("scope") != DECISION_SCOPE or decision.get("conclusion") not in {
        "postpone_dwg_keep_dxf_pdf_v1", "require_dwg_for_first_release"
    }:
        errors.append("DWG decision scope/conclusion is invalid")
    if decision.get("core_profile") != "dxf_pdf_v1" or decision.get("candidate_manifest_sha256") != probe.get("candidate_manifest_sha256"):
        errors.append("DWG decision candidate/profile binding mismatch")
    choice = decision.get("dwg_release_decision")
    if choice == "postpone_keep_dxf_pdf_baseline":
        if decision.get("conclusion") != "postpone_dwg_keep_dxf_pdf_v1":
            errors.append("postpone decision conclusion mismatch")
    elif choice == "first_release_required":
        if probe_time is None or decided is None or decided < probe_time:
            errors.append("required DWG decision predates the validated candidate")
        if dwg.get("status") != "available_verified_evaluation_only" or decision.get("conclusion") != "require_dwg_for_first_release":
            errors.append("required DWG lacks authorized actual round-trip evidence")
        cad = approval.get("target_cad", {})
        errors.extend(_validate_dwg_cad_record(cad, dwg))
    else:
        errors.append("DWG release decision is invalid")
    return errors


def validate_development(evidence: Path, approval: dict, probe: dict) -> list[str]:
    """Development direction is separate from named manufacturing approval."""
    errors = _validate_approval_contract(approval, probe)
    hashes = probe.get("validated_candidate_hashes")
    if not isinstance(hashes, dict) or not hashes or not exact_hashes(hashes):
        errors.append("development probe does not bind exact existing candidate bytes")
    try:
        direction = load(ROOT / "docs/decisions/B02-development-baseline.json")
        if (direction.get("scope") != "B02 development baseline"
            or direction.get("status") != "user_direction_accepted"
            or direction.get("manufacturing_approval") != "pending"
            or direction.get("autocad_compatibility") != "unverified"
            or direction.get("candidate_manifest_sha256") != probe.get("candidate_manifest_sha256")):
            errors.append("development direction/candidate binding is invalid")
        matrix = load(evidence / "lead-matrix.json")
        if (matrix.get("status") != "passed" or matrix.get("rule_id") != "short-edge-paper-v1"
            or len(matrix.get("cases", [])) < 9
            or not exact_hashes(matrix.get("artifact_hashes", {}))
            or not matrix.get("artifact_hashes")
            or sum(c.get("status") == "passed" for c in matrix["cases"]) < 6
            or sum(c.get("status") == "rejected_as_expected" for c in matrix["cases"]) < 2
            or not all(c.get("status") in {"passed", "rejected_as_expected"} for c in matrix["cases"])):
            errors.append("actual lead boundary/scale matrix is incomplete or changed")
        cad = load(evidence / "freecad/summary.json")
        if (cad.get("candidate_manifest_sha256") != probe.get("candidate_manifest_sha256")
            or cad.get("product") != "FreeCAD" or cad.get("version") != "0.19.2"
            or cad.get("host") != "5090-qmh" or cad.get("docker") is not False
            or cad.get("tests_completed") is not True
            or cad.get("compatibility_status") != "limited"
            or len(cad.get("pages", [])) != 3
            or not cad.get("limitations") or not cad.get("artifact_hashes")
            or not exact_hashes(cad["artifact_hashes"])):
            errors.append("actual host FreeCAD test evidence is incomplete or changed")
        gui = load(evidence / "freecad/gui-attempt.json")
        if not _artifact(gui.get("log")) or not gui.get("candidate_hashes") or not exact_hashes(gui["candidate_hashes"]):
            errors.append("FreeCAD GUI attempt evidence is missing or changed")
        required = {"open_dxf", "edit_outline_and_text", "explicit_dimension_update",
                    "save_fcstd", "close_fcstd", "reopen_fcstd_verify_edits", "export_dxf",
                    "close_before_dxf_reopen", "reopen_exported_dxf", "close_exported_dxf"}
        expected = _candidate_artifacts(probe)
        for item in cad.get("pages", []):
            record = _artifact(item.get("record"))
            if not record:
                errors.append("FreeCAD page operation record missing")
                continue
            row = load(record[0])
            source = _artifact(row.get("candidate"))
            if (not source or expected.get(source[0].resolve()) != source[1]
                or not all(row.get("steps", {}).get(k) is True for k in required)
                or not _artifact(row.get("fcstd")) or not _artifact(row.get("output"))):
                errors.append("FreeCAD operation does not bind exact input and both saved formats")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"development evidence unavailable: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--stage", choices=("development", "delivery"), default="delivery")
    args = parser.parse_args()
    decision_md = (ROOT / args.decision).resolve() if not args.decision.is_absolute() else args.decision.resolve()
    evidence = (ROOT / args.evidence).resolve() if not args.evidence.is_absolute() else args.evidence.resolve()
    probe = load(evidence / "validation" / "probe-result.json")
    dwg = load(evidence / "dwg" / "capability.json")
    decision = load(decision_md.with_suffix(".json"))
    approval = load(evidence / "human-approval.json")
    technical_ok = probe.get("status") == "passed" and len(probe.get("pages", [])) == 3 and probe.get("candidate_immutable") is True
    approval_errors = (validate_development(evidence, approval, probe) if args.stage == "development"
                       else validate_approval(approval, probe)) if technical_ok else []
    decision_errors = validate_decision(decision, probe, dwg, approval) if technical_ok else []
    blockers = ([] if technical_ok else ["DXF/PDF technical validation is not passed"]) + approval_errors + decision_errors
    status = "passed" if technical_ok and not blockers else "blocked" if technical_ok else "failed"
    result = {
        "status": status,
        "stage": args.stage,
        "formal_delivery_status": "approved" if args.stage == "delivery" and status == "passed" else "pending",
        "autocad_compatibility": "unverified" if args.stage == "development" else "requires_named_evidence",
        "freecad_compatibility": "limited" if args.stage == "development" else "not_an_autocad_substitute",
        "core_dxf_pdf_gate": ("passed_development_only" if args.stage == "development" else "passed") if technical_ok and not approval_errors else "technical_pass_human_pending" if technical_ok else "failed",
        "dwg_probe_result": dwg.get("status"),
        "dwg_release_decision": decision.get("dwg_release_decision"),
        "blockers": blockers, "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    write_path = evidence / "gate-result.json"
    write_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if status == "passed" else 2 if status == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
