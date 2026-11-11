"""Lock and validate one exact Simplified Chinese font face."""

from __future__ import annotations

from pathlib import Path

import hashlib
from typing import Any

from fontTools.ttLib import TTCollection, TTFont


class GlyphCoverageError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_runtime_font(profile: dict[str, Any], project_root: Path) -> Path:
    source = Path(profile["source_collection_path"])
    output = project_root / profile["render_font_path"]
    if not source.is_file():
        if output.is_file() and sha256_file(output) == profile["extracted_face_sha256"]:
            return output
        raise GlyphCoverageError(f"font collection is missing: {source}")
    if sha256_file(source) != profile["source_collection_sha256"]:
        raise GlyphCoverageError("font collection hash mismatch")
    collection = TTCollection(str(source), lazy=False)
    index = int(profile["collection_face_index"])
    if index >= len(collection.fonts):
        raise GlyphCoverageError("configured font face index is unavailable")
    face = collection.fonts[index]
    family = face["name"].getDebugName(1)
    postscript = face["name"].getDebugName(6)
    if family != profile["face_family"] or postscript != profile["face_postscript_name"]:
        raise GlyphCoverageError("configured font face identity mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.is_file() or sha256_file(output) != profile["extracted_face_sha256"]:
        face.recalcTimestamp = False
        face.save(str(output), reorderTables=False)
    if sha256_file(output) != profile["extracted_face_sha256"]:
        raise GlyphCoverageError("extracted SC face hash mismatch")
    return output


def supported_codepoints(path: Path, face_index: int | None = None) -> set[int]:
    if not path.is_file():
        raise GlyphCoverageError(f"font file is missing: {path}")
    if path.suffix.lower() in {".ttc", ".otc"}:
        if face_index is None:
            raise GlyphCoverageError("TTC/OTC coverage requires an exact face index")
        fonts = [TTCollection(str(path)).fonts[face_index]]
    else:
        fonts = [TTFont(str(path), lazy=True)]
    points: set[int] = set()
    for font in fonts:
        for table in font["cmap"].tables:
            points.update(table.cmap)
    return points


def check_glyph_coverage(path: Path, texts: list[str], *, face_index: int | None = None) -> dict:
    points = supported_codepoints(path, face_index)
    required = {ord(character) for text in texts for character in text if not character.isspace()}
    missing = sorted(required - points)
    if missing:
        display = " ".join(f"U+{value:04X}" for value in missing)
        raise GlyphCoverageError(f"font lacks required glyphs: {display}")
    return {
        "font": str(path),
        "font_sha256": sha256_file(path),
        "face_index": face_index,
        "required_codepoints": len(required),
        "missing_codepoints": [],
        "critical_symbols": {character: ord(character) in points for character in "Ω±（）－；：。"},
    }
