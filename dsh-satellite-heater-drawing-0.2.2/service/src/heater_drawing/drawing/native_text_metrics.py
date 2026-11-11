"""Measure controlled HZ MTEXT with the actual CAD font renderer.

Noto is too wide to certify the original single-line technical requirement.
An isolated native vector plot measures the visible glyphs, with a coloured
reference square to recover the actual page transform instead of assuming it.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

import ezdxf
from ezdxf.math import Matrix44
import pymupdf

_CACHE = {}


def union_bounds(boxes):
    # Rect.union treats a horizontal/vertical stroke as an empty rectangle.
    # These zero-area boxes are real visible glyph/calibration paths.
    return pymupdf.Rect(min(box.x0 for box in boxes), min(box.y0 for box in boxes),
                        max(box.x1 for box in boxes), max(box.y1 for box in boxes))


def measure_hz_mtext(entity, fonts: dict, factor: float, offset_x: float):
    from .opencadstudio import NativeCadError, NativeSession, font_paths, resolve_executable

    copied = entity.copy()
    copied.transform(Matrix44.scale(1 / factor))
    original = copied.dxf.insert
    copied.dxf.insert = (20, 1100, 0)
    try:
        copied.discard_xdata("HEATER_DRAWING")
    except ezdxf.DXFValueError:
        pass
    executable = resolve_executable()
    stat = executable.stat()
    attributes = {name: str(value) for name, value in copied.dxf.all_existing_dxf_attribs().items()
                  if name not in {"handle", "owner"}}
    key = (copied.text, json.dumps(attributes, sort_keys=True), str(executable),
           stat.st_size, stat.st_mtime_ns, fonts["original_hzdx_shx"]["sha256"],
           fonts["cad_style_font_file"], fonts["cad_style_bigfont_file"], fonts["cad_style_width_factor"])
    if key not in _CACHE:
        document = ezdxf.new("R2018")
        document.header["$INSUNITS"] = 4
        document.styles.add(fonts["cad_style_name"], font=fonts["cad_style_font_file"],
                            dxfattribs={"bigfont": fonts["cad_style_bigfont_file"],
                                        "width": fonts["cad_style_width_factor"]})
        if copied.dxf.layer not in document.layers:
            document.layers.add(copied.dxf.layer, color=7)
        document.modelspace().add_entity(copied)
        # The red square cannot be confused with the controlled black HZ text.
        document.modelspace().add_lwpolyline([(10, 10), (20, 10), (20, 20), (10, 20)],
                                             close=True, dxfattribs={"color": 1})
        controlled = {"directory": Path(fonts["native_template_directory"]), "fonts": fonts}
        with tempfile.TemporaryDirectory(prefix="heater-hz-metrics-") as folder:
            root = Path(folder)
            source, pdf = root / "glyph.dxf", root / "glyph.pdf"
            document.saveas(source)
            with NativeSession(root, font_paths(controlled), executable=str(executable)) as session:
                session.call({"op": "open", "path": str(source)})
                state = session.call({"protocol": 1, "op": "state"})
                if state.get("missing_fonts"):
                    raise NativeCadError(f"Native HZ metrics font missing: {state['missing_fonts']}")
                session.operation("plot", path=str(pdf), layout="Model", area="window",
                                  window=[0, 0, 841, 1189],
                                  paper="ISO_full_bleed_A0_(841.00_x_1189.00_MM)",
                                  orientation="Portrait", fit=False, scale="1:1",
                                  center=False, offset_x=0, offset_y=0,
                                  lineweights=False, stamp=False)
            with pymupdf.open(pdf) as rendered:
                paths = rendered[0].get_drawings()
            references, glyphs = [], []
            for path in paths:
                stroke, fill = path.get("color"), path.get("fill")
                if stroke and all(abs(a-b) < 1e-6 for a, b in zip(stroke, (1, 0, 0))):
                    references.append(pymupdf.Rect(path["rect"]))
                elif ((stroke is not None and max(stroke) < 1e-6)
                      or (fill is not None and max(fill) < 1e-6)):
                    glyphs.append(pymupdf.Rect(path["rect"]))
            if not references or not glyphs:
                raise NativeCadError(f"Cannot isolate native HZ glyphs and calibration square: {len(references)} reference paths, {len(glyphs)} glyph paths")
            square = union_bounds(references)
            sx, sy = square.width / 10, square.height / 10
            if sx <= 0 or abs(sx-sy) > 1e-4:
                raise NativeCadError(f"Native glyph measurement has an invalid page transform: {list(square)}, scales={sx},{sy}, reference paths={len(references)}")
            visible = union_bounds(glyphs)
            left = (visible.x0 - square.x0) / sx + 10 - 20
            right = (visible.x1 - square.x0) / sx + 10 - 20
            bottom = (square.y1 - visible.y1) / sy + 10 - 1100
            top = (square.y1 - visible.y0) / sy + 10 - 1100
            # A0 is deliberately much larger than the legal text block. Detect
            # clipping explicitly so a clipped plot can never certify a fit.
            if min(visible.x0, visible.y0) < 1 or visible.x1 > 841*sx-1 or visible.y1 > 1189*sy-1:
                raise NativeCadError("Native glyph probe touches its measurement page boundary")
            _CACHE[key] = (left, bottom, right, top)
            if len(_CACHE) > 2048:
                oldest = next(iter(_CACHE))
                del _CACHE[oldest]
    left, bottom, right, top = _CACHE[key]
    return (original.x - offset_x/factor + left, original.y + bottom,
            original.x - offset_x/factor + right, original.y + top)
