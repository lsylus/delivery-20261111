#!/usr/bin/env python3
"""Revalidate a B05 candidate against its frozen revision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from heater_drawing.delivery import DeliveryError, validate_delivery
from heater_drawing.domain.models import Revision


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=ROOT / "templates/heater-a4-v1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        revision = Revision.model_validate_json(args.expected.read_text(encoding="utf-8"))
        result = validate_delivery(args.directory, revision, template_dir=args.template)
    except (OSError, ValueError, DeliveryError) as exc:
        code = exc.code if isinstance(exc, DeliveryError) else "VALIDATION_FAILED"
        result = {"schema_version": 1, "status": "failed", "error_code": code, "message": str(exc)}
        _write(args.output, result)
        return 1
    _write(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
