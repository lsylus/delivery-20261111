"""Merge only explicitly ordered, validated single-page PDFs."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter


def merge_single_page_pdfs(inputs: list[Path], output: Path) -> None:
    if not inputs:
        raise ValueError("PDF merge requires at least one explicit input")
    writer = PdfWriter()
    for path in inputs:
        reader = PdfReader(str(path), strict=True)
        if len(reader.pages) != 1:
            raise ValueError(f"single-page PDF has {len(reader.pages)} pages: {path.name}")
        writer.add_page(reader.pages[0])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        writer.write(stream)
