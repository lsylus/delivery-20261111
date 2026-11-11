"""Separate native process for B02 STEP validation; bounded by probe_native caller."""
import argparse
import json
from pathlib import Path
from thermal_drawings.importers.native import inspect_step_geometry


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    try:
        result = inspect_step_geometry(a.input)
        code = 0
    except Exception as exc:
        result = dict(status='failed', error_type=type(exc).__name__, reason=str(exc))
        code = 1
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
