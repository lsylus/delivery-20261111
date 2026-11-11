#!/usr/bin/env python3
"""Generate editable DWG plus per-code/merged PDFs directly from Excel."""
import argparse
import json
from pathlib import Path
from heater_drawing.delivery.generate import generate_from_excel
from heater_drawing.delivery.validation import DeliveryError

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=ROOT / "templates/heater-a4-v1")
    parser.add_argument("--name", default="加热器图纸")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = generate_from_excel(args.input, template_dir=args.template,
                                     output=args.output, package_name=args.name)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error_code": (
            exc.code if isinstance(exc, DeliveryError) else "BUILD_FAILED"
        ), "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
