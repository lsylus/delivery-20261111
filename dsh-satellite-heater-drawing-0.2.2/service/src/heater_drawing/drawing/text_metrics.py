"""Exact CAD text metrics for the locked OpenType face."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import math
from pathlib import Path
from typing import Any

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTCollection, TTFont


class FontMetricError(ValueError):
    pass


@lru_cache(maxsize=4)
def _load(path: str, face_index: int) -> TTFont:
    source = Path(path)
    if not source.is_file():
        raise FontMetricError(f"font metric source is missing: {source}")
    if source.suffix.lower() in {".ttc", ".otc"}:
        return TTCollection(str(source), lazy=False).fonts[face_index]
    return TTFont(str(source), lazy=False)


def locked_font_path(profile: dict[str, Any]) -> tuple[Path, int]:
    """Resolve the exact locked face from the source collection or extracted runtime face."""
    source = Path(profile["source_collection_path"])
    if source.is_file():
        expected = profile["source_collection_sha256"]
        index = int(profile["collection_face_index"])
    else:
        root = Path(__file__).resolve().parents[4]
        source = root / profile["render_font_path"]
        expected = profile["extracted_face_sha256"]
        index = 0
    if not source.is_file():
        raise FontMetricError(f"font metric source is missing: {source}")
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise FontMetricError(f"locked font hash mismatch: {source}")
    return source, index


def locked_font(profile: dict[str, Any]) -> TTFont:
    path, index = locked_font_path(profile)
    return _load(str(path), index)


def font_constants(profile: dict[str, Any]) -> tuple[int, int]:
    font = locked_font(profile)
    units_per_em = int(font["head"].unitsPerEm)
    cap_height = int(font["OS/2"].sCapHeight)
    if units_per_em != int(profile["units_per_em"]) or cap_height != int(profile["cap_height_units"]):
        raise FontMetricError("locked font em/cap-height metrics do not match the manifest")
    return units_per_em, cap_height


def em_size_for_cap_height(cap_height_mm: float, profile: dict[str, Any]) -> float:
    units_per_em, cap_units = font_constants(profile)
    return float(cap_height_mm) * units_per_em / cap_units


def advance_width_mm(text: str, cap_height_mm: float, profile: dict[str, Any], width_factor: float = 1.0) -> float:
    font = locked_font(profile)
    _, cap_units = font_constants(profile)
    cmap = font.getBestCmap() or {}
    metrics = font["hmtx"].metrics
    missing = sorted({character for character in text if ord(character) not in cmap})
    if missing:
        raise FontMetricError("locked font lacks glyphs: " + " ".join(f"U+{ord(c):04X}" for c in missing))
    units = sum(metrics[cmap[ord(character)]][0] for character in text)
    return units / cap_units * float(cap_height_mm) * float(width_factor)


def _outline_metrics(text: str, profile: dict[str, Any]) -> tuple[float, tuple[float, float, float, float]]:
    font = locked_font(profile)
    cmap = font.getBestCmap() or {}
    glyphs = font.getGlyphSet()
    metrics = font["hmtx"].metrics
    pen_x = 0.0
    bounds: list[tuple[float, float, float, float]] = []
    for character in text:
        name = cmap.get(ord(character))
        if name is None:
            raise FontMetricError(f"locked font lacks glyph: U+{ord(character):04X}")
        pen = BoundsPen(glyphs)
        glyphs[name].draw(pen)
        if pen.bounds is not None:
            x_min, y_min, x_max, y_max = pen.bounds
            bounds.append((pen_x + x_min, y_min, pen_x + x_max, y_max))
        pen_x += metrics[name][0]
    if not bounds:
        return pen_x, (0.0, 0.0, pen_x, 0.0)
    return pen_x, (
        min(item[0] for item in bounds), min(item[1] for item in bounds),
        max(item[2] for item in bounds), max(item[3] for item in bounds),
    )


def text_transform_mm(
    text: str,
    point: tuple[float, float],
    cap_height_mm: float,
    profile: dict[str, Any],
    alignment: str,
    width_factor: float = 1.0,
    rotation: float = 0.0,
) -> dict[str, float]:
    advance_units, outline = _outline_metrics(text, profile)
    _, cap_units = font_constants(profile)
    scale_y = float(cap_height_mm) / cap_units
    scale_x = scale_y * float(width_factor)
    advance = advance_units * scale_x
    raw_left, raw_bottom, raw_right, raw_top = (
        outline[0] * scale_x,
        outline[1] * scale_y,
        outline[2] * scale_x,
        outline[3] * scale_y,
    )
    if alignment in {"MIDDLE_CENTER", "CENTER", "TOP_CENTER", "BOTTOM_CENTER"}:
        local_x = -advance / 2
    elif alignment in {"RIGHT", "MIDDLE_RIGHT", "TOP_RIGHT", "BOTTOM_RIGHT"}:
        local_x = -advance
    else:
        local_x = 0.0
    if alignment.startswith("TOP"):
        local_y = -raw_top
    elif alignment.startswith("BOTTOM"):
        local_y = -raw_bottom
    elif alignment.startswith("MIDDLE"):
        local_y = -(raw_bottom + raw_top) / 2
    else:
        local_y = 0.0
    return {
        "anchor_x": float(point[0]),
        "anchor_y": float(point[1]),
        "local_x": local_x,
        "local_y": local_y,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "rotation": float(rotation),
        "raw_left": raw_left,
        "raw_bottom": raw_bottom,
        "raw_right": raw_right,
        "raw_top": raw_top,
    }


def transform_point_mm(x: float, y: float, transform: dict[str, float]) -> tuple[float, float]:
    local_x = x * transform["scale_x"] + transform["local_x"]
    local_y = y * transform["scale_y"] + transform["local_y"]
    angle = math.radians(transform["rotation"])
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        transform["anchor_x"] + local_x * cosine - local_y * sine,
        transform["anchor_y"] + local_x * sine + local_y * cosine,
    )


def aligned_box_mm(
    text: str,
    point: tuple[float, float],
    cap_height_mm: float,
    profile: dict[str, Any],
    alignment: str,
    width_factor: float = 1.0,
    rotation: float = 0.0,
) -> tuple[float, float, float, float]:
    transform = text_transform_mm(
        text, point, cap_height_mm, profile, alignment, width_factor, rotation
    )
    _, outline = _outline_metrics(text, profile)
    corners = [
        transform_point_mm(x, y, transform)
        for x, y in (
            (outline[0], outline[1]),
            (outline[0], outline[3]),
            (outline[2], outline[1]),
            (outline[2], outline[3]),
        )
    ]
    return (
        min(point[0] for point in corners),
        min(point[1] for point in corners),
        max(point[0] for point in corners),
        max(point[1] for point in corners),
    )


def box_inside(box: tuple[float, float, float, float], bounds: list[float], tolerance: float = 0.1) -> bool:
    left, bottom, right, top = box
    return (
        left >= bounds[0] - tolerance
        and bottom >= bounds[1] - tolerance
        and right <= bounds[2] + tolerance
        and top <= bounds[3] + tolerance
    )
