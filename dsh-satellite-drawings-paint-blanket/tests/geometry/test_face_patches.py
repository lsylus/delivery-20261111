import math
from unittest.mock import Mock
import cadquery as cq
import pytest
from OCP.TopoDS import TopoDS_Shape
from b03_cases import patch_cases, rectangle
from geometry_core import solid_pairs as m

@pytest.mark.parametrize('name,a,b,areas',list(patch_cases()))
@pytest.mark.parametrize('fuzzy',[None,1e-7])
def test_analytic_patch_cases(name,a,b,areas,fuzzy):
    r=m.intersect_face_patches(a,b,fuzzy_tolerance_mm=fuzzy)
    assert r.completed and r.failure_stage is None
    assert sorted(f.Area() for f in r.patches)==pytest.approx(areas,rel=1e-6,abs=1e-9)

def test_strict_area_boundary():
    f=rectangle(w=1,h=1)
    area=m.intersect_face_patches(f,f).patches[0].Area()
    for limit,wanted in [(math.nextafter(area,0),1),(area,0),(math.nextafter(area,math.inf),0)]:
        r=m.intersect_face_patches(f,f,minimum_patch_area_mm2=limit)
        assert r.completed and len(r.patches)==wanted

@pytest.mark.parametrize('where',['build','done','shape','cast','area'])
def test_native_exception_is_incomplete_with_stage(monkeypatch,where):
    f=rectangle();op=Mock();op.IsDone.return_value=True;op.Shape.return_value=f.wrapped
    monkeypatch.setattr(m,'_common_operation',Mock(return_value=op))
    if where=='build': m._common_operation.side_effect=RuntimeError('injected')
    elif where=='done': op.IsDone.side_effect=RuntimeError('injected')
    elif where=='shape': op.Shape.side_effect=RuntimeError('injected')
    elif where=='cast': monkeypatch.setattr(cq.Shape,'cast',Mock(side_effect=RuntimeError('injected')))
    else: monkeypatch.setattr(cq.Face,'Area',Mock(side_effect=RuntimeError('injected')))
    r=m.intersect_face_patches(f,f)
    assert not r.completed and r.patches==() and r.failure_stage=='face_intersection'
    assert 'injected' in r.failure_message

def test_incomplete_and_successful_null_are_distinct(monkeypatch):
    op=Mock(); monkeypatch.setattr(m,'_common_operation',lambda *a:op)
    op.IsDone.return_value=False
    r=m.intersect_face_patches(rectangle(),rectangle())
    assert not r.completed and not r.patches
    op.Shape.assert_not_called()
    op.IsDone.return_value=True;op.Shape.return_value=TopoDS_Shape()
    r=m.intersect_face_patches(rectangle(),rectangle())
    assert r.completed and not r.patches and r.failure_stage is None

@pytest.mark.parametrize('key',['fuzzy_tolerance_mm','minimum_patch_area_mm2'])
@pytest.mark.parametrize('value',[0,-1,True,math.nan,math.inf])
def test_bad_numerical_parameters_are_programming_errors(key,value):
    with pytest.raises(ValueError): m.intersect_face_patches(rectangle(),rectangle(),**{key:value})

@pytest.mark.parametrize('fuzzy,parallel',[(None,None),(1e-7,False)])
def test_common_options_set_before_first_build(monkeypatch,fuzzy,parallel):
    a=rectangle();op=Mock();factory=Mock(return_value=op)
    monkeypatch.setattr(m,'BRepAlgoAPI_Common',factory)
    assert m.build_common_operation(a.wrapped,a.wrapped,fuzzy_tolerance_mm=fuzzy,run_parallel=parallel) is op
    factory.assert_called_once_with()  # Two-shape constructor builds too early.
    op.SetArguments.assert_called_once();op.SetTools.assert_called_once()
    op.SetNonDestructive.assert_called_once_with(True)
    if fuzzy is None: op.SetFuzzyValue.assert_not_called()
    else: op.SetFuzzyValue.assert_called_once_with(fuzzy)
    if parallel is None: op.SetRunParallel.assert_not_called()
    else: op.SetRunParallel.assert_called_once_with(False)
    assert op.mock_calls[-1][0]=='Build'

def test_patch_result_cannot_claim_partial_success():
    with pytest.raises(ValueError): m.FacePatchIntersection(False,(rectangle(),))

def test_nonfinite_patch_area_is_not_success(monkeypatch):
    f=rectangle()
    monkeypatch.setattr(cq.Face,'Area',lambda self:math.nan)
    r=m.intersect_face_patches(f,f)
    assert not r.completed and not r.patches
