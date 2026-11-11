import math
import cadquery as cq
import pytest
from geometry_core.transforms import *
from geometry_core.bounds import BoundsStrategy,measure_shape_bounds

@pytest.mark.parametrize('rotation,translation',[
    ([[1,0,0],[0,1,0],[0,0,-1]],[0,0,0]),
    ([[2,0,0],[0,1,0],[0,0,1]],[0,0,0]),
    ([[1,0,0],[0,1,0],[0,0,1]],[math.nan,0,0]),
    ([[1,0,0],[0,1,0],[0,0,math.inf]],[0,0,0]),
    ([[1,0],[0,1]],[0,0,0]),
])
def test_reject_non_rigid(rotation,translation):
    with pytest.raises(ValueError):rigid_transform_from_values(rotation,translation)

def test_composition_inverse_and_source_is_unchanged(graph):
    parent=graph.node((1,1)).world_transform;local=graph.node((1,1,2)).local_transform
    computed=compose(parent,local);expected=graph.node((1,1,2)).world_transform
    assert computed.translation_mm==pytest.approx(expected.translation_mm,abs=1e-9)
    for a,b in zip(computed.rotation,expected.rotation):assert a==pytest.approx(b,abs=1e-9)
    shape=cq.Solid.makeBox(2,3,4).wrapped
    exact=BoundsStrategy.OPTIMAL_WITHOUT_SHAPE_TOLERANCE
    before=measure_shape_bounds(shape,strategy=exact)
    tr=rigid_transform_from_values([[0,-1,0],[1,0,0],[0,0,1]],[10,20,30])
    moved=move_topods_shape(shape,tr)
    assert measure_shape_bounds(moved,strategy=exact).values==pytest.approx([7,20,30,10,22,34],abs=1e-6)
    restored=move_topods_shape(moved,tr,inverse=True)
    assert measure_shape_bounds(restored,strategy=exact).values==pytest.approx(before.values,abs=1e-6)
    assert measure_shape_bounds(shape,strategy=exact)==before

def test_bounds_strategies_are_explicit():
    shape=cq.Solid.makeSphere(3).wrapped
    exact=measure_shape_bounds(shape,strategy=BoundsStrategy.OPTIMAL_WITHOUT_SHAPE_TOLERANCE)
    conservative=measure_shape_bounds(shape,strategy=BoundsStrategy.CONSERVATIVE_WITHOUT_TRIANGULATION)
    assert all(a<=b+1e-9 for a,b in zip(conservative.minimum,exact.minimum))
    assert all(a>=b-1e-9 for a,b in zip(conservative.maximum,exact.maximum))
    with pytest.raises(ValueError):measure_shape_bounds(shape,strategy='exact-ish')
