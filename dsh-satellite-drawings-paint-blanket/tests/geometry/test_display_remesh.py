import cadquery as cq
import numpy as np
import pytest
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from geometry_core.display_triangles import triangle_payload,tessellate_face


def face():
    shape=cq.Solid.makeCylinder(20,30).rotate((0,0,0),(1,0,0),37).translate((123,456,789))
    return next(f for f in shape.Faces() if f.geomType()=='CYLINDER')


def test_normal_payload_preserves_order_and_exact_duplicate_audit():
    points=[cq.Vector(0,0,0),cq.Vector(1,0,0),cq.Vector(0,1,0),cq.Vector(0,0,0)]
    positions,normals,collapsed,emitted,area=triangle_payload(points,[(0,1,2),(0,3,1)])
    assert emitted==[0] and area==pytest.approx(.5)
    assert len(positions)==len(normals)==3
    assert collapsed[0]['source_triangle']==1 and collapsed[0]['reason']=='exact_duplicate_coordinates'
    assert collapsed[0]['twice_area_mm2']==0


def test_normal_face_records_precision_without_remeshing():
    *payload,diagnostic=tessellate_face(face(),.1,.1)
    assert len(payload[0])>0 and payload[3]
    assert diagnostic['remeshed'] is False and diagnostic['effective']['relative'] is True
    assert diagnostic['maximum_angular_tolerance_rad']==.1


def test_single_native_remesh_keeps_world_placement_and_source_unchanged(monkeypatch):
    original=cq.Face.tessellate;source=face();calls=[]
    def initial_bad_only(current,*args):
        calls.append((current,args))
        points,triangles=original(current,*args)
        if len(calls)==1:
            n=len(points)
            return [*points,cq.Vector(0,0,0),cq.Vector(1,0,0),cq.Vector(1,1e-16,0)],[*triangles,(n,n+1,n+2)]
        return points,triangles
    monkeypatch.setattr(cq.Face,'tessellate',initial_bad_only)
    positions,normals,collapsed,emitted,area,diagnostic=tessellate_face(source,.1,.1)
    assert len(calls)==2 and calls[0][0] is source and calls[1][0] is not source
    retry=calls[1][0]
    assert retry.Center().toTuple()==pytest.approx(source.Center().toTuple(),abs=1e-10)
    assert retry.wrapped.Orientation()==source.wrapped.Orientation()
    assert diagnostic['remeshed'] is True and diagnostic['effective']['relative'] is False
    assert diagnostic['maximum_angular_tolerance_rad']==.35
    assert diagnostic['reason']=='initial_degenerate_tessellation_triangle'
    assert len(positions)==3*len(emitted)>0 and np.isfinite(normals).all()
    assert area==pytest.approx(source.Area(),rel=.01)
    assert all(np.linalg.norm(np.cross(b-a,c-a))>1e-15 for a,b,c in positions.reshape(-1,3,3))
    assert BRep_Tool.Triangulation_s(retry.wrapped,TopLoc_Location()) is not None
    # Initial sampling may cache on source, but retry cannot replace that mesh.
    assert BRep_Tool.Triangulation_s(source.wrapped,TopLoc_Location()).NbTriangles()!=0


@pytest.mark.parametrize('third',[(1.,1e-16,0.),(2.,0.,0.)])
def test_degenerate_retry_still_fails_with_original_rule(monkeypatch,third):
    original=cq.Face.tessellate;calls=[]
    def bad_every_time(current,*args):
        calls.append(current);points,triangles=original(current,*args);n=len(points)
        return [*points,cq.Vector(0,0,0),cq.Vector(1,0,0),cq.Vector(*third)],[*triangles,(n,n+1,n+2)]
    monkeypatch.setattr(cq.Face,'tessellate',bad_every_time)
    with pytest.raises(ValueError,match='degenerate tessellation triangle'):
        tessellate_face(face(),.1,.1)
    assert len(calls)==2


def test_invalid_native_face_and_unrelated_errors_do_not_retry(monkeypatch):
    source=face();original=cq.Face.tessellate;calls=[]
    def bad(current,*args):
        calls.append(current);points,triangles=original(current,*args);n=len(points)
        return [*points,cq.Vector(0,0,0),cq.Vector(1,0,0),cq.Vector(2,0,0)],[*triangles,(n,n+1,n+2)]
    monkeypatch.setattr(cq.Face,'tessellate',bad)
    monkeypatch.setattr(cq.Face,'isValid',lambda current:False)
    with pytest.raises(ValueError,match='invalid native face'):
        tessellate_face(source,.1,.1)
    assert len(calls)==1
    monkeypatch.setattr(cq.Face,'tessellate',lambda current,*args:([],[]))
    with pytest.raises(ValueError,match='face has no triangles'):
        tessellate_face(source,.1,.1)


def test_absolute_premesh_precision_is_recorded_without_mode_change():
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    source=face()
    mesh=BRepMesh_IncrementalMesh(source.wrapped,1.,False,.5,False)
    assert mesh.IsDone()
    *payload,diagnostic=tessellate_face(source,1.,.5,relative=False)
    assert diagnostic['remeshed'] is False
    assert diagnostic['initial']==diagnostic['effective']==dict(linear_deflection_mm=1.,angular_deflection_rad=.5,relative=False)
    assert diagnostic['maximum_tolerance_mm']==1.
    assert diagnostic['maximum_angular_tolerance_rad']==.5


def test_nonfinite_payload_does_not_attempt_degeneracy_recovery(monkeypatch):
    calls=[]
    def nonfinite(current,*args):
        calls.append(current)
        return [cq.Vector(float('nan'),0,0),cq.Vector(1,0,0),cq.Vector(0,1,0)],[(0,1,2)]
    monkeypatch.setattr(cq.Face,'tessellate',nonfinite)
    with pytest.raises(ValueError,match='non-finite tessellation position'):
        tessellate_face(face(),.1,.1)
    assert len(calls)==1


def zero_measure_planar_face(endpoint=(1,0,0)):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Pln,gp_Pnt,gp_Dir
    edges=[cq.Edge.makeLine((0,0,0),endpoint),cq.Edge.makeLine(endpoint,(0,0,0))]
    wire=cq.Wire.assembleEdges(edges)
    maker=BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0,0,0),gp_Dir(0,0,1)),wire.wrapped,True)
    assert maker.IsDone()
    return cq.Face(maker.Face())


def test_zero_measure_planar_catalog_retains_native_face_without_meshing():
    from geometry_core.display_triangles import classify_unrenderable_face
    source=zero_measure_planar_face()
    original=(source.isValid(),source.Area(),source._uvBounds(),len(source.Edges()))
    diagnostic=classify_unrenderable_face(source)
    assert diagnostic['reason']=='zero_measure_planar_face'
    assert diagnostic['native_valid'] is True and diagnostic['native_retained'] is True
    assert diagnostic['source_triangles']==0 and diagnostic['native_area_mm2']==0
    assert diagnostic['edge_count']==2
    assert diagnostic['threshold']==dict(maximum_absolute_area_mm2=1e-9,maximum_endpoint_line_distance_mm=1e-7)
    assert (source.isValid(),source.Area(),source._uvBounds(),len(source.Edges()))==original
    assert BRep_Tool.Triangulation_s(source.wrapped,TopLoc_Location()) is None


def test_zero_measure_catalog_rejects_nonzero_surfaces_and_tiny_four_edge_faces():
    from geometry_core.display_triangles import classify_unrenderable_face
    square=cq.Face.makeFromWires(cq.Wire.makePolygon([cq.Vector(0,0,0),cq.Vector(1,0,0),cq.Vector(1,1,0),cq.Vector(0,1,0)],close=True))
    thin=cq.Face.makeFromWires(cq.Wire.makePolygon([cq.Vector(0,0,0),cq.Vector(1e-4,0,0),cq.Vector(1e-4,1e-6,0),cq.Vector(0,1e-6,0)],close=True))
    assert classify_unrenderable_face(square) is None
    assert len(thin.Edges())==4 and thin.Area()<1e-9
    assert classify_unrenderable_face(thin) is None
    assert classify_unrenderable_face(face()) is None


@pytest.mark.parametrize('area,uv',[(1e-8,(0.,1.,0.,0.)),(float('nan'),(0.,1.,0.,0.)),(0.,(0.,float('inf'),0.,0.))])
def test_zero_measure_catalog_does_not_relax_thresholds_or_accept_nonfinite(monkeypatch,area,uv):
    from geometry_core.display_triangles import classify_unrenderable_face
    source=zero_measure_planar_face()
    monkeypatch.setattr(cq.Face,'Area',lambda current:area)
    monkeypatch.setattr(cq.Face,'_uvBounds',lambda current:uv)
    assert classify_unrenderable_face(source) is None


@pytest.mark.parametrize('angle',[0,17,90,137])
def test_zero_measure_catalog_is_rotation_invariant(angle):
    from geometry_core.display_triangles import classify_unrenderable_face
    radians=np.radians(angle)
    source=zero_measure_planar_face((10*np.cos(radians),10*np.sin(radians),0))
    if angle==17:
        # Both native UV spans are substantial, but their transverse width is zero.
        u0,u1,v0,v1=source._uvBounds()
        assert min(u1-u0,v1-v0)>1
    source=source.rotate((0,0,0),(1,2,3),37).translate((123,456,789))
    diagnostic=classify_unrenderable_face(source)
    assert diagnostic is not None and diagnostic['endpoint_diameter_mm']==pytest.approx(10)
    assert diagnostic['maximum_endpoint_line_distance_mm']<=1e-7
    assert BRep_Tool.Triangulation_s(source.wrapped,TopLoc_Location()) is None


def test_zero_measure_catalog_rejects_noncollinear_endpoints(monkeypatch):
    from geometry_core.display_triangles import classify_unrenderable_face
    source=zero_measure_planar_face()
    # Native area alone cannot establish collinearity, even with exactly 2 LINE edges.
    edges=[cq.Edge.makeLine((0,0,0),(1,0,0)),cq.Edge.makeLine((1,0,0),(0,1e-5,0))]
    monkeypatch.setattr(cq.Face,'Edges',lambda current:edges)
    assert source.Area()==0 and classify_unrenderable_face(source) is None


def test_zero_measure_catalog_accepts_finite_coincident_endpoints(monkeypatch):
    from geometry_core.display_triangles import classify_unrenderable_face
    source=zero_measure_planar_face()
    monkeypatch.setattr(cq.Edge,'startPoint',lambda current:cq.Vector(123,456,789))
    monkeypatch.setattr(cq.Edge,'endPoint',lambda current:cq.Vector(123,456,789))
    diagnostic=classify_unrenderable_face(source)
    assert diagnostic is not None and diagnostic['endpoint_diameter_mm']==0
    assert diagnostic['maximum_endpoint_line_distance_mm']==0
    assert diagnostic['common_line_direction'] is None


def test_zero_measure_catalog_rejects_nonfinite_endpoints(monkeypatch):
    from geometry_core.display_triangles import classify_unrenderable_face
    source=zero_measure_planar_face()
    monkeypatch.setattr(cq.Edge,'endPoint',lambda current:cq.Vector(float('nan'),0,0))
    assert classify_unrenderable_face(source) is None



def test_valid_nonzero_face_initially_empty_recovers_once_on_private_fine_mesh(monkeypatch):
    original=cq.Face.tessellate;source=face();calls=[]
    assert source.isValid() and source.Area()>1
    def initially_empty(current,*args):
        calls.append((current,args))
        return ([],[]) if len(calls)==1 else original(current,*args)
    monkeypatch.setattr(cq.Face,'tessellate',initially_empty)
    positions,normals,collapsed,emitted,area,diagnostic=tessellate_face(source,1.,.5,relative=False)
    assert len(calls)==2 and calls[0][0] is source and calls[1][0] is not source
    assert calls[1][1]==(.1,.35)
    assert len(positions)==len(normals)==3*len(emitted)>0
    assert area==pytest.approx(source.Area(),rel=.01)
    assert diagnostic['remeshed'] is True and diagnostic['reason']=='initial_empty_tessellation'
    assert diagnostic['initial_source_triangles']==0 and diagnostic['source_triangles']>0
    assert diagnostic['initial']==dict(linear_deflection_mm=1.,angular_deflection_rad=.5,relative=False)
    assert diagnostic['effective']==dict(linear_deflection_mm=.1,angular_deflection_rad=.35,relative=False)
    assert diagnostic['maximum_tolerance_mm']==1.
    assert diagnostic['maximum_angular_tolerance_rad']==.5


def test_valid_face_still_empty_after_one_retry_keeps_original_empty_error(monkeypatch):
    source=face();calls=[]
    def always_empty(current,*args):
        calls.append(current)
        return [],[]
    monkeypatch.setattr(cq.Face,'tessellate',always_empty)
    with pytest.raises(ValueError,match='^face has no triangles; refusing incomplete display map$'):
        tessellate_face(source,1.,.5,relative=False)
    assert len(calls)==2 and calls[0] is source and calls[1] is not source


def test_invalid_native_empty_face_remains_catalogable_without_retry(monkeypatch):
    source=zero_measure_planar_face();calls=[]
    def always_empty(current,*args):
        calls.append(current)
        return [],[]
    monkeypatch.setattr(cq.Face,'tessellate',always_empty)
    monkeypatch.setattr(cq.Face,'isValid',lambda current:False)
    with pytest.raises(ValueError,match='^face has no triangles; refusing incomplete display map$'):
        tessellate_face(source,1.,.5,relative=False)
    assert calls==[source]
    from geometry_core.display_triangles import classify_unrenderable_face
    assert classify_unrenderable_face(source)['native_valid'] is False
