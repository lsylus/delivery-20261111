#!/usr/bin/env python3
"""Build one isolated, fully verified B05 delivery candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from heater_drawing.delivery import DeliveryError, build_delivery
from heater_drawing.domain.models import Revision


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", type=Path, required=True)
    parser.add_argument("--dxf", type=Path, required=True)
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--original", type=Path, default=ROOT / "fixtures/case/加热器图纸.xlsx")
    parser.add_argument("--template", type=Path, default=ROOT / "templates/heater-a4-v1")
    parser.add_argument("--name", default="加热器图纸")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        revision = Revision.model_validate_json(args.revision.read_text(encoding="utf-8"))
        result = build_delivery(
            revision,
            input_dxf=args.dxf,
            pages_path=args.pages,
            original_workbook=args.original,
            output=args.output,
            template_dir=args.template,
            package_name=args.name,
        )
    except (OSError, ValueError, DeliveryError) as exc:
        code = exc.code if isinstance(exc, DeliveryError) else "BUILD_FAILED"
        print(json.dumps({"status": "failed", "error_code": code, "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
