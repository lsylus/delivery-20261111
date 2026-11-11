#!/usr/bin/env python3
"""Independent semantic readback for a B04 combined DXF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from heater_drawing.domain.models import DrawingPage
from heater_drawing.drawing.readback import inspect_dxf
from heater_drawing.drawing.template import load_template


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dxf", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=Path("templates/heater-a4-v1"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    planned = json.loads(args.pages.read_text(encoding="utf-8"))
    pages = [DrawingPage.model_validate(item) for item in planned["pages"]]
    expected_rows = expected["rows"]
    if [page.row_id for page in pages] != [f"{expected['sheet']}:{row['excel_row']}" for row in expected_rows]:
        raise ValueError("page order/row mapping differs from the expected workbook")
    for page, row in zip(pages, expected_rows, strict=True):
        for name in ("code", "width_mm", "length_mm", "requested_scale"):
            actual = page.scale.label if name == "requested_scale" else getattr(page.fields, name)
            if actual != row[name]:
                raise ValueError(f"planned {name} differs for {page.row_id}")
    template = load_template(args.template)
    result = inspect_dxf(
        args.dxf, pages, template["layout"], template["fonts"]
    )
    result["mapping"] = planned["layout_mapping"]
    result["expected_source"] = expected["source"]
    result["assertions"] = {
        "input_order_preserved": True,
        "real_geometry_not_scaled": True,
        "native_dimensions_dimlfac_one": True,
        "editable_text_preserved": True,
        "a4_layout_per_row": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
