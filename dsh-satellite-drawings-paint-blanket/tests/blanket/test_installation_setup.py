import copy
import math
import cadquery as cq
import pytest
from helpers import ROOT,model_for,fixture,check
from thermal_drawings.blanket.installation import measure
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.selection import Frame,shape_hash
from thermal_drawings.paint.selection import Model,Occurrence,PaintError

def setup(**kw):return dict(x_direction=[1,0,0],rotation_deg=0,origin_mode='bounds_min',offset_mm=[0,0],**kw)
def source_case(angle=0):
    source=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
    bottom=min((f for f in source.Faces() if f.geomType()=='PLANE'),key=lambda f:f.Center().z)
    if angle:
        source=source.rotate((0,0,0),(1,2,3),angle).translate((13,-11,7))
        bottom=bottom.rotate((0,0,0),(1,2,3),angle).translate((13,-11,7))
    model=model_for(source)
    ref=next(r for _,f,r in model.faces if (f.Center()-bottom.Center()).Length<1e-6)
    direction=cq.Edge.makeLine((0,0,0),(1,0,0)).rotate((0,0,0),(1,2,3),angle).tangentAt().toTuple()
    return source,model,ref,dict(setup(),x_direction=list(direction))

@pytest.mark.parametrize('angle',[0,31])
def test_frame_full_motor_covariant_and_positive_clearance(angle,tmp_path):
    source,model,ref,options=source_case(angle);before=shape_hash(source)
    report=measure(model,ref,options);frame=report['frame']
    assert report['source_face_count']==44 and report['units']=='mm'
    assert report['section_x_open_interval_mm'][0]<40<300<334<report['section_x_open_interval_mm'][1]
    assert math.isclose(report['local_bounds_mm'][1][0],369,abs_tol=.01)
    p,_=fixture();p.update(model_ref=model.model_ref,target_instances=[ref['instance_id']],installation_face=ref,installation_frame=frame,installation_setup=options,envelope_policy='faceted_clearance_v1',clearance_options=dict(clearance_mm=1,section_cuts_mm=[40,300,334]))
    p['allowance']['factors']=[1,1,1]
    result=generate(p,model,'from-measured-frame',tmp_path)
    assert result['status']=='needs_review' and len(result['panels'])==34
    from thermal_drawings.blanket.seams import adjacency
    edges,seams=adjacency(result['panels'])
    # Exact native polyline corners retain all 76 paired physical subedges;
    # closed-wire sampling previously lost 1–2 pairs after tiny frame shifts.
    assert len(seams)==76 and len(edges)==172
    assert max(len(panel['outer_loop']['points']) for panel in result['panels'])==16
    assert check(result,'volume_ratio')['observed']['ratio']==pytest.approx(1.1304395,abs=1e-6)
    manufacturing=cq.Shape.importBrep(str(tmp_path/'manufacturing.brep'))
    assert min(f.distance(source) for f in manufacturing.Faces())>.99999
    assert shape_hash(source)==before
    p['installation_frame']=copy.deepcopy(frame);p['installation_frame']['origin'][0]+=.01
    with pytest.raises(ValueError,match='preview_mismatch'):generate(p,model,'tampered')

def test_axes_origin_projection_units_and_repeated_instance_binding():
    source,model,ref,options=source_case();original=measure(model,ref,options)
    for changes in [dict(rotation_deg=90),dict(x_direction=[-1,0,0]),dict(origin_mode='face_center'),dict(offset_mm=[10,-20])]:
        actual=measure(model,ref,dict(options,**changes));f=actual['frame']
        x,y,z=map(lambda k:cq.Vector(*f[k]),['x_axis','y_axis','z_axis'])
        assert x.cross(y).dot(z)==pytest.approx(1)
        assert abs(Frame(f).local(source).BoundingBox().zmin)<1e-6
        assert f!=original['frame']
    shifted=measure(model,ref,dict(options,offset_mm=[10,-20]))
    assert shifted['section_x_open_interval_mm'][0]==pytest.approx(original['section_x_open_interval_mm'][0]-10)
    # The importer normalizes units to mm; measurement uses the actual size,
    # without treating every equipment occurrence as the motor dimensions.
    box=cq.Solid.makeBox(25.4,50.8,76.2);m=model_for(box);bottom=min(m.faces,key=lambda row:row[1].Center().z)[2]
    report=measure(m,bottom,setup());assert report['local_bounds_mm'][1][0]==pytest.approx(25.4,abs=1e-5)
    moved=source.translate((1000,0,0));m2=model_for(moved,'copy');combined=Model(model.model_ref,[model.occurrences[0],m2.occurrences[0]])
    ref2=next(r for _,f,r in m2.faces if abs(f.Center().z-ref['signature']['centroid_mm'][2])<1e-7 and f.geomType()=='PLANE')
    second=measure(combined,ref2,options);assert second['instance_id']=='copy'
    assert second['frame']['origin'][0]==pytest.approx(original['frame']['origin'][0]+1000,abs=1e-6)
    stale=copy.deepcopy(ref);stale['model_revision']+=1
    with pytest.raises(PaintError,match='Missing or ambiguous exact FaceRef'):measure(combined,stale,options)

@pytest.mark.parametrize('changes',[dict(x_direction=[0,0,0]),dict(x_direction=[0,0,1]),dict(rotation_deg=181),dict(offset_mm=[float('nan'),0]),dict(offset_mm=[1e7,0])])
def test_bad_axis_or_origin_rejected(changes):
    _,model,ref,options=source_case()
    with pytest.raises(ValueError):measure(model,ref,dict(options,**changes))

def test_wrong_installation_plane_rejected():
    _,model,ref,options=source_case()
    cylinder=next(r for _,f,r in model.faces if f.geomType()=='CYLINDER')
    with pytest.raises(ValueError,match='requires_plane'):measure(model,cylinder,options)
    shoulder=next(r for _,f,r in model.faces if f.geomType()=='PLANE' and f.normalAt().z>.99 and 180<f.Center().z<190)
    with pytest.raises(ValueError,match='supporting_bottom'):measure(model,shoulder,options)
