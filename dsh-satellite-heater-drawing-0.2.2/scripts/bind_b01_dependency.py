#!/usr/bin/env python3
"""Bind a current-source B01 runner result for a later Batch dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    registry = json.loads(
        (ROOT / "scripts/acceptance_registry.json").read_text(encoding="utf-8")
    )
    report_path = args.report.resolve()
    output_path = args.output.resolve()
    if not report_path.is_relative_to(ROOT) or not output_path.is_relative_to(ROOT):
        parser.error("report and output must be inside the project root")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    b01 = registry["batches"]["B01"]
    consumer = registry["batches"][args.consumer]
    dependency = next(
        item for item in consumer["dependency_reports"] if item["batch"] == "B01"
    )
    if report["status"] != "passed" or report["batch"] != "B01":
        raise ValueError("B01 report must be passed")
    payload = {
        "schema_version": 1,
        "batch": "B01",
        "report_path": report_path.relative_to(ROOT).as_posix(),
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "source_git_head": report["source_git_head"],
        "source_contract_sha256": report["source_contract_sha256"],
        "commands": [
            {
                "id": item["id"],
                "argv": item["argv"],
                "required": item.get("required", True),
                "kind": item.get("kind"),
            }
            for item in b01["commands"]
        ],
        "required_checks": [item["id"] for item in report["checks"]],
        "input_paths": sorted(report["input_hashes"]),
        "artifact_paths": sorted(report["artifact_hashes"]),
        "boundary_inputs": sorted(
            [b01["boundary_evidence"]["path"], b01["boundary_evidence"]["baseline_path"]]
        ),
        "historical_accepted_report": dependency["historical_accepted_report"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"path": output_path.relative_to(ROOT).as_posix(), "status": "bound"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
