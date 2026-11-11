#!/usr/bin/env python3
"""Export deterministic JSON Schema snapshots from the contract models."""

from __future__ import annotations

import json
from pathlib import Path

from heater_drawing.domain.models import SCHEMA_MODELS, schema_snapshot

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    output = ROOT / "schemas"
    output.mkdir(parents=True, exist_ok=True)
    for name in SCHEMA_MODELS:
        (output / name).write_text(
            json.dumps(schema_snapshot(name), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
