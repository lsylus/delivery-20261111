import io, math
from unittest.mock import Mock
import cadquery as cq
import pytest
from OCP.TopoDS import TopoDS_Shape
from b03_cases import PARAMETERS, analytic_pairs, box, face, rectangle
from geometry_core import solid_pairs as m

@pytest.mark.parametrize('name,a,b,oracle',list(analytic_pairs()))
def test_distance_volume_area_oracles(name,a,b,oracle):
    r=m.measure_shape_pair(a,b,**PARAMETERS)
    assert r.completed and r.left_valid and r.right_valid
    assert r.distance_mm==pytest.approx(oracle[0],abs=1e-6)
    assert r.intersection_volume_mm3==pytest.approx(oracle[1],rel=1e-6,abs=1e-9)
    assert r.contact_area_mm2==pytest.approx(oracle[2],rel=1e-6,abs=1e-9) if oracle[2] is not None else r.contact_area_mm2 is None

@pytest.mark.parametrize('gap',[.099,.1,.101])
def test_business_gap_never_becomes_boolean_fuzzy(gap):
    r=m.measure_shape_pair(box(),box((10+gap,0,0)),intersection_distance_limit_mm=.2,zero_volume_tolerance_mm3=1e-5)
    assert r.intersection_performed and r.completed
    assert r.distance_mm==pytest.approx(gap,abs=1e-6)
    assert r.intersection_volume_mm3==0 and r.contact_area_mm2 is None

@pytest.mark.parametrize('stage',['input_validity','distance','intersection','planar_contact'])
def test_kernel_exceptions_are_stage_errors(monkeypatch,stage):
    bad=Mock(side_effect=RuntimeError('injected native failure'))
    if stage=='input_validity': monkeypatch.setattr(m,'BRepCheck_Analyzer',bad)
    elif stage=='distance': monkeypatch.setattr(m,'BRepExtrema_DistShapeShape',bad)
    elif stage=='intersection': monkeypatch.setattr(m,'_common_operation',bad)
    else: monkeypatch.setattr(m,'measure_planar_contact_area',bad)
    with pytest.raises(m.SolidPairMeasurementError) as e: m.measure_shape_pair(box(),box((10,0,0)),**PARAMETERS)
    assert e.value.stage==stage and e.value.completed is False
    assert isinstance(e.value.__cause__,RuntimeError)

@pytest.mark.parametrize('stage',['distance','intersection'])
def test_not_done_raises_with_stage(monkeypatch,stage):
    op=Mock();op.IsDone.return_value=False
    monkeypatch.setattr(m,'BRepExtrema_DistShapeShape' if stage=='distance' else '_common_operation',lambda *a:op)
    with pytest.raises(m.SolidPairMeasurementError) as e: m.measure_shape_pair(box(),box(),**PARAMETERS)
    assert e.value.stage==stage
    op.Value.assert_not_called();op.Shape.assert_not_called()

def test_null_common_is_a_valid_zero(monkeypatch):
    op=Mock();op.IsDone.return_value=True;op.Shape.return_value=TopoDS_Shape()
    monkeypatch.setattr(m,'_common_operation',lambda *a:op)
    r=m.measure_shape_pair(box(),box((10,10,10)),**PARAMETERS)
    assert r.completed and r.intersection_volume_mm3==0 and r.contact_area_mm2 is None

def test_validity_is_not_completion(monkeypatch):
    op=Mock();op.IsValid.return_value=False
    monkeypatch.setattr(m,'BRepCheck_Analyzer',lambda *a:op)
    r=m.measure_shape_pair(box(),box((11,0,0)),**PARAMETERS)
    assert r.completed and not r.left_valid and not r.right_valid
    assert not r.intersection_performed

def test_budget_and_patch_failure_never_become_zero_or_partial_area(monkeypatch):
    a,b=box(),box((10,0,0))
    r=m.measure_planar_contact_area(a,b,maximum_face_pairs=0)
    assert not r.completed and r.area_mm2 is None and r.failure_stage=='planar_budget'
    with pytest.raises(m.SolidPairMeasurementError) as e: m.measure_shape_pair(a,b,maximum_planar_face_pairs=0,**PARAMETERS)
    assert e.value.stage=='planar_budget'
    monkeypatch.setattr(m,'intersect_face_patches',lambda *a,**kw:m.FacePatchIntersection(False,(),failure_stage='face_intersection',failure_message='injected'))
    r=m.measure_planar_contact_area(a,b)
    assert not r.completed and r.area_mm2 is None and r.failure_stage=='face_intersection'
    with pytest.raises(m.SolidPairMeasurementError) as e: m.measure_shape_pair(a,b,**PARAMETERS)
    assert e.value.stage=='face_intersection'

def test_planar_scope_and_curved_unknown():
    a=cq.Solid.makeSphere(5)
    r=m.measure_planar_contact_area(a,a.translate((10,0,0)))
    assert r.completed and r.area_mm2 is None and r.scope=='planar_faces'
    assert r.nonplanar_face_count>0

def test_measurement_leaves_brep_and_tolerances_unchanged():
    def dump(shape):
        stream=io.BytesIO();shape.exportBrep(stream);return stream.getvalue()
    a,b=box(),box((9,0,0)); before=[dump(a),dump(b)]
    m.measure_shape_pair(a,b,**PARAMETERS)
    m.intersect_face_patches(a.Faces()[0],b.Faces()[0])
    assert [dump(a),dump(b)]==before

@pytest.mark.parametrize('key,value',[(k,v) for k in ['intersection_distance_limit_mm','zero_volume_tolerance_mm3','fuzzy_tolerance_mm','minimum_contact_area_mm2'] for v in [-1,True,math.nan,math.inf]]+ [('maximum_planar_face_pairs',v) for v in [-1,True,1.5]])
def test_parameters_rejected_before_kernel(key,value):
    args={**PARAMETERS,key:value}
    with pytest.raises(ValueError):m.measure_shape_pair(box(),box(),**args)

def test_nonfinite_distance_is_failure(monkeypatch):
    op=Mock();op.IsDone.return_value=True;op.Value.return_value=math.nan
    monkeypatch.setattr(m,'BRepExtrema_DistShapeShape',lambda *a:op)
    with pytest.raises(m.SolidPairMeasurementError) as e:m.measure_shape_pair(box(),box(),**PARAMETERS)
    assert e.value.stage=='distance'

def test_actual_invalid_topology_can_complete_distance():
    crossed=face([(0,0),(10,10),(0,10),(10,0)])
    assert not crossed.isValid()
    r=m.measure_shape_pair(crossed,rectangle(z=1),**PARAMETERS)
    assert r.completed and not r.left_valid and r.right_valid
    assert r.distance_mm==pytest.approx(1,abs=1e-6)

def test_null_input_fails_at_validity():
    broken=box()
    broken.wrapped=TopoDS_Shape()  # Inject null native handle; CQ constructor rejects it.
    with pytest.raises(m.SolidPairMeasurementError) as e:
        m.measure_shape_pair(broken,box(),**PARAMETERS)
    assert e.value.stage=='input_validity'

@pytest.mark.parametrize('kind',['Value','Shape','Volume','Area'])
def test_native_result_access_failures_are_not_zero(monkeypatch,kind):
    if kind=='Value':
        op=Mock();op.IsDone.return_value=True;op.Value.side_effect=RuntimeError('read failed')
        monkeypatch.setattr(m,'BRepExtrema_DistShapeShape',lambda *a:op)
        expected='distance'
    elif kind=='Shape':
        op=Mock();op.IsDone.return_value=True;op.Shape.side_effect=RuntimeError('read failed')
        monkeypatch.setattr(m,'_common_operation',lambda *a:op)
        expected='intersection'
    else:
        monkeypatch.setattr(cq.Shape if kind=='Volume' else cq.Face,kind,Mock(side_effect=RuntimeError('read failed')))
        expected='intersection'
    a,b=(box(),box()) if kind!='Area' else (rectangle(),rectangle())
    with pytest.raises(m.SolidPairMeasurementError) as e:m.measure_shape_pair(a,b,**PARAMETERS)
    assert e.value.stage==expected

@pytest.mark.parametrize('value',[-1,math.nan,math.inf,True])
def test_fact_type_rejects_nonfinite_or_negative_values(value):
    with pytest.raises(ValueError):m.SolidPairMeasurement(value,0,None,True,True,False)
    with pytest.raises(ValueError):m.PlanarContactMeasurement(True,value)

def test_partial_planar_result_cannot_publish_area():
    with pytest.raises(ValueError):m.PlanarContactMeasurement(False,100)
