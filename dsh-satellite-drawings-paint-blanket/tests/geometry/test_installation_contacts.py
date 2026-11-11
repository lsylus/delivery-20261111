import cadquery as cq
import pytest

from geometry_core import solid_pairs as pairs


def plane(shape, axis, sign):
    return next(
        face for face in shape.Faces()
        if face.geomType() == 'PLANE' and getattr(face.normalAt(), axis) * sign > .999999
    )


def installation_pair(gap=0, support_shift=(0, 0, 0)):
    target = cq.Solid.makeBox(10, 10, 10)
    support = cq.Solid.makeBox(20, 20, 2, cq.Vector(-5, -5, -2-gap)).translate(support_shift)
    return target, support


@pytest.mark.parametrize('gap', [0, .05, .1])
def test_opposed_planar_projection_includes_maximum_gap_boundary(gap):
    target, support = installation_pair(gap)
    measured = pairs.measure_opposed_planar_face_contact(
        plane(target, 'z', -1), plane(support, 'z', 1), maximum_gap_mm=.1)
    assert measured.gap_mm == pytest.approx(gap, abs=1e-9)
    assert measured.contact_area_mm2 == pytest.approx(100)


def test_over_limit_penetration_normal_and_real_overlap_are_rejected():
    target, support = installation_pair(.100001)
    assert pairs.measure_opposed_planar_face_contact(
        plane(target, 'z', -1), plane(support, 'z', 1), maximum_gap_mm=.1) is None

    target, support = installation_pair()
    assert pairs.measure_opposed_planar_face_contact(
        plane(target, 'z', -1), plane(support, 'z', -1), maximum_gap_mm=.1) is None

    target, support = installation_pair(0, (30, 0, 0))
    assert pairs.measure_opposed_planar_face_contact(
        plane(target, 'z', -1), plane(support, 'z', 1), maximum_gap_mm=.1) is None

    # The support top is above the target bottom, so the signed gap is negative.
    target, support = installation_pair(-.05)
    assert pairs.measure_opposed_planar_face_contact(
        plane(target, 'z', -1), plane(support, 'z', 1), maximum_gap_mm=.1) is None


def test_projection_failure_is_not_an_empty_contact(monkeypatch):
    target, support = installation_pair(.05)
    monkeypatch.setattr(
        pairs,
        'intersect_face_patches',
        lambda *args, **kwargs: pairs.FacePatchIntersection(
            False, (), 'face_intersection', 'injected projection failure'))
    with pytest.raises(pairs.SolidPairMeasurementError, match='injected projection failure') as error:
        pairs.measure_opposed_planar_face_contact(
            plane(target, 'z', -1), plane(support, 'z', 1), maximum_gap_mm=.1)
    assert error.value.stage == 'face_intersection'


def test_world_rigid_transform_preserves_pair_indices_gap_and_area():
    target, support = installation_pair(.05)
    original = pairs.find_opposed_planar_contacts(
        'target', target, [('support', support)], maximum_gap_mm=.1)
    moved = lambda shape: shape.rotate((0, 0, 0), (1, 2, 3), 37).translate((123, -45, 67))
    transformed = pairs.find_opposed_planar_contacts(
        'target', moved(target), [('support', moved(support))], maximum_gap_mm=.1)
    assert len(original) == len(transformed) == 1
    assert transformed[0].target_face_index == original[0].target_face_index
    assert transformed[0].support_face_index == original[0].support_face_index
    assert transformed[0].gap_mm == pytest.approx(.05, abs=1e-7)
    assert transformed[0].contact_area_mm2 == pytest.approx(100, abs=1e-6)


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True])
def test_maximum_gap_rejects_invalid_values(value):
    target, support = installation_pair()
    with pytest.raises(ValueError):
        pairs.find_opposed_planar_contacts(
            'target', target, [('support', support)], maximum_gap_mm=value)
