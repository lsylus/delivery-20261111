from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, DecodedStreamObject
import pytest

from heater_drawing.drawing.plot_style import apply_sample_strokes


def _pdf(path, content):
    writer = PdfWriter()
    page = writer.add_blank_page(595, 842)
    stream = DecodedStreamObject()
    stream.set_data(content)
    page.replace_contents(stream)
    with path.open("wb") as target:
        writer.write(target)


def test_sample_width_compensates_transform_and_preserves_colour_and_geometry(tmp_path):
    path = tmp_path / "plot.pdf"
    _pdf(path, b"q 2 0 0 2 0 0 cm 1 1 0 RG 0 0 m 10 0 l S Q")
    report = apply_sample_strokes(path)
    reader = PdfReader(path)
    operations = ContentStream(reader.pages[0].get_contents(), reader).operations
    assert report["stroked_paths"] == 1
    assert any(op == b"w" and abs(float(args[0]) - .36) < 1e-8 for args, op in operations)
    assert any(op == b"RG" and list(map(float, args)) == [1, 1, 0] for args, op in operations)
    assert any(op == b"l" and list(map(float, args)) == [10, 0] for args, op in operations)


def test_nonuniform_transform_is_rejected_without_replacing_native_pdf(tmp_path):
    path = tmp_path / "plot.pdf"
    _pdf(path, b"q 2 0 0 3 0 0 cm 0 0 m 10 0 l S Q")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="non-uniform"):
        apply_sample_strokes(path)
    assert path.read_bytes() == before
