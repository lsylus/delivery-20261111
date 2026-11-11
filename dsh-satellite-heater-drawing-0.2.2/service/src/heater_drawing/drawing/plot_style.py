"""Apply the engineer sample's physical stroke width to native vector PDF.

OpenCADStudio's CTB currently leaves true-colour frame widths unchanged. This
printing pass applies the same 0.72 pt width to black and yellow paths, without
changing coordinates, colours, text, or the editable DWG. It compensates for
the PDF graphics transform so width is specified in physical page points.
"""
from __future__ import annotations

import math
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, FloatObject

SAMPLE_STROKE_PT = 0.72


def apply_sample_strokes(path: Path) -> dict:
    reader = PdfReader(path, strict=True)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    count = 0
    for page in writer.pages:
        content = ContentStream(page.get_contents(), writer)
        linear = (1.0, 0.0, 0.0, 1.0)
        stack = []
        operations = []
        for args, op in content.operations:
            if op == b"q":
                stack.append(linear)
            elif op == b"Q":
                if not stack:
                    raise ValueError("Native PDF has an unbalanced graphics-state stack")
                linear = stack.pop()
            elif op == b"cm":
                a, b, c, d, _, _ = map(float, args)
                x, y, z, w = linear
                linear = (a*x + b*z, a*y + b*w, c*x + d*z, c*y + d*w)
            elif op == b"Do":
                raise ValueError("Native sample stroke policy does not support PDF XObjects")
            if op in {b"S", b"s", b"B", b"B*", b"b", b"b*"}:
                a, b, c, d = linear
                sx, sy = math.hypot(a, b), math.hypot(c, d)
                if sx <= 0 or abs(sx-sy) > 1e-6 or abs(a*c+b*d) > 1e-6:
                    raise ValueError("Native plot uses a non-uniform stroke transform")
                operations.append(([FloatObject(SAMPLE_STROKE_PT / sx)], b"w"))
                count += 1
            operations.append((args, op))
        if stack:
            raise ValueError("Native PDF has an unbalanced graphics-state stack")
        content.operations = operations
        page.replace_contents(content)
    temporary = path.with_suffix(".styled.pdf")
    try:
        with temporary.open("wb") as stream:
            writer.write(stream)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"policy": "engineer_sample_uniform_stroke_v1", "physical_width_pt": SAMPLE_STROKE_PT,
            "stroked_paths": count, "geometry_changed": False, "dwg_changed": False}
