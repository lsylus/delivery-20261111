"""Regression checks for the two real native-save interoperability defects."""
import ezdxf

from heater_drawing.drawing.dxf_writer import export_planned_dxf
from heater_drawing.drawing.readback import _dimension_cache_signature


def test_rotated_mtext_and_equivalent_direction_have_identical_semantics():
    doc = ezdxf.new("R2018")
    entity = doc.modelspace().add_mtext("25", dxfattribs={"rotation": 90, "char_height": 3.5})
    before = _dimension_cache_signature([entity], 0, 1)
    entity.dxf.text_direction = (0, 1, 0)
    del entity.dxf.rotation
    assert _dimension_cache_signature([entity], 0, 1) == before
    entity.dxf.text_direction = (1, 0, 0)
    assert _dimension_cache_signature([entity], 0, 1) != before


def test_exported_paper_viewports_reference_declared_layers(
    tmp_path, real_plan, real_revision, controlled_template,
):
    path = tmp_path / "drawing.dxf"
    export_planned_dxf(path, real_plan, real_revision, controlled_template)
    doc = ezdxf.readfile(path)
    viewports = [entity for layout in doc.layouts for entity in layout.query("VIEWPORT")]
    assert len(viewports) == 6
    assert all(entity.dxf.layer in doc.layers for entity in viewports)
