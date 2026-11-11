import cadquery as cq
import pytest

from helpers import model_for
from thermal_drawings.blanket.installation import detect
from thermal_drawings.blanket.selection import BlanketError
from thermal_drawings.paint.selection import Model


def occurrence(shape, instance):
    return model_for(shape, instance).occurrences[0]


def model(*items):
    base = model_for(cq.Solid.makeBox(1, 1, 1))
    return Model(base.model_ref, list(items))


def box_pair(gap=.05):
    target = cq.Solid.makeBox(10, 10, 10)
    support = cq.Solid.makeBox(20, 20, 2, cq.Vector(-5, -5, -2-gap))
    return target, support


def test_split_support_faces_aggregate_to_one_target_face():
    target = cq.Solid.makeBox(10, 10, 10)
    left = cq.Solid.makeBox(5, 10, 2, cq.Vector(0, 0, -2.05))
    right = cq.Solid.makeBox(5, 10, 2, cq.Vector(5, 0, -2.05))
    result = detect(model(occurrence(target, 'target'), occurrence(left, 'left'), occurrence(right, 'right')),
                    ['target'], [], .1)
    assert result['status'] == 'unique'
    assert len(result['candidates']) == 1
    candidate = result['candidates'][0]
    assert candidate['target_face_ref']['instance_id'] == 'target'
    assert candidate['support_face_ref']['instance_id'] == 'left'
    assert [ref['instance_id'] for ref in candidate['support_face_refs']] == ['left', 'right']
    assert candidate['gap_mm'] == pytest.approx(.05)
    assert candidate['contact_area_mm2'] == pytest.approx(100)


def test_distinct_target_faces_are_ambiguous_without_axis_heuristics():
    target = cq.Solid.makeBox(10, 10, 10)
    below = cq.Solid.makeBox(10, 10, 2, cq.Vector(0, 0, -2.05))
    left = cq.Solid.makeBox(2, 10, 10, cq.Vector(-2.05, 0, 0))
    result = detect(model(occurrence(target, 'target'), occurrence(below, 'below'), occurrence(left, 'left')),
                    ['target'], [], .1)
    assert result['status'] == 'ambiguous'
    assert len(result['candidates']) == 2
    assert {tuple(round(v, 6) for v in c['target_face_ref']['signature']['normal'])
            for c in result['candidates']} == {(-1, 0, 0), (0, 0, -1)}


def test_none_exclusions_and_transformed_world_occurrences():
    target, support = box_pair()
    excluded = detect(model(occurrence(target, 'target'), occurrence(support, 'support')),
                      ['target'], ['support'], .1)
    assert excluded['status'] == 'none' and excluded['candidates'] == []

    moved = lambda shape: shape.rotate((0, 0, 0), (1, 2, 3), 37).translate((123, -45, 67))
    result = detect(model(occurrence(moved(target), 'target'), occurrence(moved(support), 'support')),
                    ['target'], [], .1)
    assert result['status'] == 'unique'
    assert result['candidates'][0]['gap_mm'] == pytest.approx(.05, abs=1e-7)
    assert result['candidates'][0]['contact_area_mm2'] == pytest.approx(100, abs=1e-6)


@pytest.mark.parametrize('targets,excluded,code', [
    ([], [], 'installation_target_required_or_duplicate'),
    (['missing'], [], 'installation_target_unknown'),
    (['target'], ['target'], 'installation_target_required'),
])
def test_scope_errors_are_explicit(targets, excluded, code):
    target, support = box_pair()
    with pytest.raises(BlanketError, match=code):
        detect(model(occurrence(target, 'target'), occurrence(support, 'support')),
               targets, excluded, .1)
