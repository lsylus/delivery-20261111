"""Real installed-CAD checks, including tampering after all hashes are rebound."""
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest
import pymupdf
import ezdxf
from openpyxl import load_workbook
from pypdf import PdfReader

from heater_drawing.delivery.generate import generate_from_excel
from heater_drawing.delivery import DeliveryError, validate_delivery
from heater_drawing.domain.models import Revision
from heater_drawing.drawing.opencadstudio import DEFAULT_EXECUTABLE
from .conftest import ROOT, rebind_candidate

pytestmark = pytest.mark.skipif(
    not Path(os.environ.get("HEATER_OPENCADSTUDIO", DEFAULT_EXECUTABLE)).is_file(),
    reason="real OpenCADStudio native executable is not installed",
)


@pytest.fixture(scope="module")
def native_case(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-case") / "package"
    result = generate_from_excel(ROOT / "fixtures/case/加热器图纸.xlsx",
                                 template_dir=ROOT / "templates/heater-a4-v1", output=root)
    revision = Revision.model_validate_json((root / "revision.json").read_text())
    return root, revision, result


def test_real_excel_to_native_dwg_and_matching_three_page_pdf(native_case):
    root, revision, result = native_case
    assert result["status"] == "passed" and result["page_count"] == 3
    assert (root / "加热器图纸.dwg").read_bytes()[:6] == b"AC1032"
    assert len(PdfReader(root / "加热器图纸.pdf").pages) == 3
    cad = json.loads((root / "cad-report.json").read_text())
    assert cad["verified_save"]["verified"] is True
    assert cad["verified_reverse_save"]["verified"] is True
    assert cad["readback"]["inspection"]["native_dimension_entities"] == 6
    assert cad["dimension_style"]["font"] == "txt.shx"
    assert cad["dimension_style"]["width_factor"] == .85
    assert cad["dimension_style"]["overrides"]["dimtxt"] == 5
    drawing = ezdxf.readfile(root / "加热器图纸.dxf")
    for name, expected in {"dimtad": 1, "dimexo": .625, "dimexe": 1.25}.items():
        assert drawing.dimstyles.get("HEATER_DIM").dxf.get(name) == expected
    assert [item["geometry_mm"] for item in cad["readback"]["inspection"]["pages"]] == [
        {"width": 25.0, "length": 25.0}, {"width": 30.0, "length": 50.0},
        {"width": 100.0, "length": 300.0},
    ]
    assert [item["row_id"] for item in cad["render_reports"]] == revision.expected_row_ids
    assert all(item["stroke_style"]["physical_width_pt"] == .72 for item in cad["render_reports"])
    for page in cad["readback"]["inspection"]["pages"]:
        technical = next(item for item in page["text_measurements"] if "/technical/" in item["identity"])
        assert technical["measurement_backend"] == "opencadstudio_hz_vector_glyphs"
        assert len(technical["text"].splitlines()) == 9
        assert abs(technical["point_paper_mm"][0] - 131.751634520231) < 1e-6
        assert abs(technical["point_paper_mm"][1] - 98.231739238227) < 1e-6
        assert technical["box_paper_mm"][2] < 200
    workbook = load_workbook(root / "actual.xlsx")
    assert workbook["Sheet1"]["O3"].value == "郑玲"
    workbook.close()


def test_native_footer_preserves_all_four_sample_glyphs_without_overlap_or_clipping(native_case):
    root, _, _ = native_case
    # Source sample path bounds in PDF points. Whitespace in the CAD fallback
    # previously placed the first 页 on top of 第 and the last 页 off the page.
    expected = [(459.98, 467.09), (502.07, 508.19), (532.31, 539.27), (570.14, 576.26)]
    with pymupdf.open(root / "加热器图纸.pdf") as pdf:
        for page in pdf:
            intervals = sorted((path["rect"].x0, path["rect"].x1)
                               for path in page.get_drawings()
                               if path["color"] is not None and max(path["color"]) < 1e-6
                               and path["rect"].y0 > 825 and path["rect"].y1 < 840
                               and path["rect"].x0 > 450 and path["rect"].width < 10)
            clusters = []
            for left, right in intervals:
                if not clusters or left - clusters[-1][1] > 10:
                    clusters.append([left, right])
                else:
                    clusters[-1][1] = max(clusters[-1][1], right)
            assert len(clusters) == 4
            for actual, reference in zip(clusters, expected, strict=True):
                assert max(abs(a-b) for a, b in zip(actual, reference)) < .5
            stage_glyphs = [path["rect"] for path in page.get_drawings()
                            if 275 < path["rect"].x0 < 340 and path["rect"].x1 < 345
                            and 788 < path["rect"].y0 and path["rect"].y1 < 804
                            and path["rect"].width < 10]
            assert stage_glyphs
            assert abs(min(r.x0 for r in stage_glyphs) - 279.74) < .5
            assert abs(max(r.x1 for r in stage_glyphs) - 323.57) < .5


def test_missing_converter_never_publishes_partial_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv("HEATER_OPENCADSTUDIO", str(tmp_path / "missing"))
    output = tmp_path / "result"
    with pytest.raises(DeliveryError, match="NATIVE_CAD_FAILED"):
        generate_from_excel(ROOT / "fixtures/case/加热器图纸.xlsx",
                            template_dir=ROOT / "templates/heater-a4-v1", output=output)
    assert not output.exists()


def test_native_hz_metrics_reject_overflowing_quantity_without_publishing(tmp_path):
    source = tmp_path / "long-quantity.xlsx"
    workbook = load_workbook(ROOT / "fixtures/case/加热器图纸.xlsx")
    workbook["Sheet1"]["H2"] = "76片" + "（备份13片）" * 30
    workbook.save(source)
    workbook.close()
    output = tmp_path / "not-published"
    with pytest.raises(DeliveryError, match="UNRESOLVED_ERROR"):
        generate_from_excel(source, template_dir=ROOT / "templates/heater-a4-v1", output=output)
    assert not output.exists()


def test_rehashed_damaged_dwg_is_rejected_by_real_reopen(native_case, tmp_path):
    source, revision, _ = native_case
    root = tmp_path / "copy"
    shutil.copytree(source, root)
    dwg = root / "加热器图纸.dwg"
    dwg.write_bytes(b"AC1032" + b"invalid native drawing" * 64)
    digest = hashlib.sha256(dwg.read_bytes()).hexdigest()
    manifest = json.loads((root / "manifest.json").read_text())
    cad = json.loads((root / "cad-report.json").read_text())
    cad["dwg_sha256"] = digest
    for reports in (manifest["render_reports"], cad["render_reports"]):
        for report in reports:
            report["source_dwg_sha256"] = digest
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    (root / "cad-report.json").write_text(json.dumps(cad, ensure_ascii=False))
    rebind_candidate(root)
    with pytest.raises(DeliveryError, match="DWG_READBACK_FAILED"):
        validate_delivery(root, revision, template_dir=ROOT / "templates/heater-a4-v1")
