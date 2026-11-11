from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import ezdxf


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APPROVAL_CONTRACT = json.loads(
    (PROJECT_ROOT / "scripts/b02_approval_contract.json").read_text(encoding="utf-8")
)
APPROVAL_SCOPE = APPROVAL_CONTRACT["approval_scope"]
DECISION_SCOPE = "B02 first-release DWG scope"
DXF_ACTIONS = {
    name: True
    for name in APPROVAL_CONTRACT["dxf_actions"]
}
DWG_ACTIONS = {
    name: True
    for name in APPROVAL_CONTRACT["dwg_actions"]
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _item(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
    }


def _write_dxf(path: Path, offset: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = ezdxf.new("R2018")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_line((offset, 0), (offset + 10, 10))
    document.saveas(path)


def _copy_real_scripts(root: Path) -> None:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for name in (
        "check_format_gate.py",
        "verify_batch.py",
        "check_source_boundary.py",
        "evidence_common.py",
        "b02_approval_contract.json",
    ):
        shutil.copyfile(PROJECT_ROOT / "scripts" / name, scripts / name)


def _base_fixture(root: Path) -> tuple[dict, dict, dict]:
    _copy_real_scripts(root)
    evidence = root / "docs/evidence/B02-fix-3"
    candidate = root / "candidate/input.dxf"
    reopened = root / "cad/reopened.dxf"
    _write_dxf(candidate, 0)
    _write_dxf(reopened, 1)
    screenshot = root / "cad/screen.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\nTEST_FIXTURE_ONLY")

    now = datetime.now(timezone.utc)
    built_at = (now - timedelta(minutes=4)).isoformat()
    performed_at = (now - timedelta(minutes=3)).isoformat()
    decided_at = (now - timedelta(minutes=2)).isoformat()
    operator = {
        "id": "controlled-integration-01",
        "name": "Controlled Integration Engineer",
    }
    candidate_item = _item(root, candidate)
    reopened_item = _item(root, reopened)
    dxf_record = root / "cad/dxf-record.json"
    _write_json(
        dxf_record,
        {
            "approval_claim": "none",
            "evidence_kind": "target_cad_edit_save_reopen",
            "operator": operator,
            "performed_at": performed_at,
            "actions": DXF_ACTIONS,
            "input": candidate_item,
            "output": reopened_item,
        },
    )
    target_cad = {
        "product": "AutoCAD",
        "version": "2018",
        "operator": operator,
        "performed_at": performed_at,
        "actions": DXF_ACTIONS,
        "input": candidate_item,
        "output": reopened_item,
        "evidence_record": _item(root, dxf_record),
        "screenshots": [_item(root, screenshot)],
    }
    for relative in (
        "fixtures/synthetic/heater_sample.json",
        "templates/heater-a4-v1/layout.json",
        "templates/heater-a4-v1/fonts.json",
        "templates/heater-a4-v1/manifest.json",
    ):
        _write_json(root / relative, {"test_fixture_only": True, "approval_claim": "none"})
    template = root / "templates/heater-a4-v1/template.dxf"
    template.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, template)
    template_manifest_sha = _sha256(root / "templates/heater-a4-v1/manifest.json")
    layout_sha = _sha256(root / "templates/heater-a4-v1/layout.json")
    fonts_sha = _sha256(root / "templates/heater-a4-v1/fonts.json")
    face_sha = "f" * 64
    candidate_manifest = candidate.parent / "candidate-manifest.json"
    _write_json(
        candidate_manifest,
        {
            "profile": "dxf_pdf_v1",
            "template": {
                "manifest_sha256": template_manifest_sha,
                "layout_sha256": layout_sha,
                "fonts_sha256": fonts_sha,
            },
            "font": {"font_sha256": face_sha},
            "test_fixture_only": True,
        },
    )
    manifest_item = _item(root, candidate_manifest)
    candidate_hashes = {
        candidate_item["path"]: candidate_item["sha256"],
        manifest_item["path"]: manifest_item["sha256"],
    }
    probe = {
        "approval_claim": "none",
        "status": "passed",
        "pages": [{"test": 1}, {"test": 2}, {"test": 3}],
        "candidate_immutable": True,
        "candidate_built_at": built_at,
        "candidate_manifest_sha256": manifest_item["sha256"],
        "validated_candidate_hashes": candidate_hashes,
        "test_fixture_only": True,
    }
    approval = {
        "approval_claim": "none",
        "status": "approved",
        "actor": operator["id"],
        "decided_at": decided_at,
        "scope": APPROVAL_SCOPE,
        "conclusion": "approved_for_dxf_pdf_v1",
        "candidate": {
            "path": "candidate",
            "profile": "dxf_pdf_v1",
            "candidate_manifest_sha256": manifest_item["sha256"],
            "template_manifest_sha256": template_manifest_sha,
            "layout_sha256": layout_sha,
        },
        "font": {
            "profile_sha256": fonts_sha,
            "extracted_face_sha256": face_sha,
        },
        "target_cad": target_cad,
        "artifact_hashes": candidate_hashes,
    }
    decision = {
        "approval_claim": "none",
        "status": "approved",
        "actor": operator["id"],
        "decided_at": decided_at,
        "scope": DECISION_SCOPE,
        "conclusion": "postpone_dwg_keep_dxf_pdf_v1",
        "core_profile": "dxf_pdf_v1",
        "candidate_manifest_sha256": probe["candidate_manifest_sha256"],
        "dwg_release_decision": "postpone_keep_dxf_pdf_baseline",
    }
    _write_json(evidence / "validation/probe-result.json", probe)
    _write_json(evidence / "human-approval.json", approval)
    return probe, approval, decision


def _add_dwg_fixture(root: Path, approval: dict, *, fake_binding: bool) -> dict:
    source = root / "dwg/converted.dwg"
    output = root / "dwg/reopened.dwg"
    fake = root / "dwg/unrelated.dwg"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"AC1032" + b"\x00" * 2048)
    output.write_bytes(b"AC1032" + b"\x01" * 2048)
    fake.write_bytes(b"AC1032" + b"\x02" * 2048)
    screenshot = root / "dwg/screen.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\nTEST_FIXTURE_ONLY")
    operator = {
        "id": "controlled-integration-02",
        "name": "Controlled Integration Operator",
    }
    performed_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    dwg_record = root / "dwg/dwg-record.json"
    record = {
        "approval_claim": "none",
        "evidence_kind": "target_cad_dwg_edit_save_reopen",
        "operator": operator,
        "performed_at": performed_at,
        "product": "AutoCAD",
        "version": "2018",
        "actions": DWG_ACTIONS,
        "input": _item(root, source),
        "output": _item(root, output),
    }
    _write_json(dwg_record, record)
    approval["target_cad"]["dwg_validation"] = {
        "product": "AutoCAD",
        "version": "2018",
        "operator": operator,
        "performed_at": performed_at,
        "actions": DWG_ACTIONS,
        "input": record["input"],
        "output": record["output"],
        "evidence_record": _item(root, dwg_record),
        "screenshots": [_item(root, screenshot)],
    }
    verified = _item(root, fake if fake_binding else source)
    return {
        "approval_claim": "none",
        "status": "available_verified_evaluation_only",
        "conversion_run": False,
        "capability": {"verified_dwg": verified},
        "test_fixture_only": True,
    }


def _prepare_case(root: Path, case: str) -> None:
    probe, approval, decision = _base_fixture(root)
    evidence = root / "docs/evidence/B02-fix-3"
    dwg = {
        "approval_claim": "none",
        "status": "blocked",
        "conversion_run": False,
        "capability": {"state": "not_configured"},
        "test_fixture_only": True,
    }
    if case == "pending_negative":
        decision = {
            "approval_claim": "none",
            "status": "pending",
            "actor": None,
            "decided_at": None,
            "scope": DECISION_SCOPE,
            "conclusion": None,
            "core_profile": "dxf_pdf_v1",
            "candidate_manifest_sha256": probe["candidate_manifest_sha256"],
            "dwg_release_decision": "pending_user_decision",
        }
    elif case == "postpone_state_negative":
        dwg = _add_dwg_fixture(root, approval, fake_binding=False)
    elif case in {
        "required_blocked_negative",
        "required_fake_verified_negative",
        "required_controlled_positive",
    }:
        decision["conclusion"] = "require_dwg_for_first_release"
        decision["dwg_release_decision"] = "first_release_required"
        if case != "required_blocked_negative":
            dwg = _add_dwg_fixture(
                root,
                approval,
                fake_binding=case == "required_fake_verified_negative",
            )
    _write_json(evidence / "human-approval.json", approval)
    _write_json(evidence / "dwg/capability.json", dwg)
    _write_json(root / "docs/decisions/format-profile.json", decision)
    approval_path = evidence / "human-approval.json"
    registry = {
        "schema_version": 1,
        "approval_claim": "none",
        "batches": {
            "B99": {
                "dependency_reports": [],
                "human_gates": [
                    {
                        "id": "controlled-integration-approval",
                        "evidence_path": "docs/evidence/B02-fix-3/human-approval.json",
                        "sha256": _sha256(approval_path),
                    }
                ],
                "builtin_checks": ["format-evidence"],
                "commands": [
                    {
                        "id": "check-format-gate",
                        "argv": [
                            "{python}",
                            "scripts/check_format_gate.py",
                            "--decision",
                            "docs/decisions/format-profile.md",
                            "--evidence",
                            "docs/evidence/B02-fix-3",
                        ],
                        "kind": "command",
                        "required": True,
                        "blocked_exit_codes": [2],
                    }
                ],
            }
        },
    }
    _write_json(root / "scripts/acceptance_registry.json", registry)


def test_full_cli_dwg_decision_matrix(tmp_path: Path) -> None:
    cases = {
        "postpone_positive": (0, "passed", "passed"),
        "pending_negative": (2, "blocked", "blocked"),
        "postpone_state_negative": (1, "failed", "passed"),
        "required_blocked_negative": (1, "failed", "blocked"),
        "required_fake_verified_negative": (1, "failed", "blocked"),
        "required_controlled_positive": (0, "passed", "passed"),
    }
    results = []
    for case, expected in cases.items():
        root = tmp_path / case
        root.mkdir()
        _prepare_case(root, case)
        report = Path("docs/evidence/B02-fix-3/cli-runner") / case
        argv = [
            sys.executable,
            str(root / "scripts/verify_batch.py"),
            "B99",
            "--report-dir",
            str(report),
        ]
        completed = subprocess.run(
            argv,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        summary = json.loads((root / report / "summary.json").read_text(encoding="utf-8"))
        gate = json.loads(
            (root / "docs/evidence/B02-fix-3/gate-result.json").read_text(
                encoding="utf-8"
            )
        )
        assert (completed.returncode, summary["status"], gate["status"]) == expected
        results.append(
            {
                "case": case,
                "verify_batch_cli_exit": completed.returncode,
                "verify_batch_status": summary["status"],
                "check_format_gate_status": gate["status"],
                "check_format_gate_blockers": gate["blockers"],
                "checks": [
                    {"id": item["id"], "status": item["status"]}
                    for item in summary["checks"]
                ],
                "commands": [
                    {
                        "id": item["id"],
                        "exit_code": item["exit_code"],
                        "status": item["status"],
                    }
                    for item in summary["commands"]
                ],
            }
        )
    output = os.environ.get("B02_CLI_MATRIX_RESULTS")
    if output:
        _write_json(
            Path(output),
            {
                "schema_version": 1,
                "test_fixture_only": True,
                "approval_claim": "none; all artifacts were created in pytest temporary directories",
                "execution": "subprocess CLI execution of copied real check_format_gate.py and verify_batch.py",
                "cases": results,
            },
        )
