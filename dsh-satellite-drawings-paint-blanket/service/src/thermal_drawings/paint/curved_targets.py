"""Native target charts and local feature domains, no XY projection of curves."""
import math
import cadquery as cq
from ..blanket.developable import Developable
from ..blanket.segmentation import piecewise
from ..blanket.panels import NetError
from .selection import Plane, face_polygon, Budget

def inspect_target(face,source_ref,deflection_mm=0.5):
    if not face.isValid():raise NetError('invalid_target_face')
    if face.geomType() in ('PLANE','CYLINDER','CONE'):
        chart=Developable(face).report()
    else:
        chart=piecewise(face,deflection_mm)
    wires=[]
    for i,w in enumerate([face.outerWire(),*face.innerWires()]):
        points,_=w.sample(0.05)
        wires.append(dict(role='outer' if i==0 else 'hole',world_mm=[list(p.toTuple()) for p in points]))
    return dict(schema_version=1,algorithm_version='b13-native-target-v1',source_ref=source_ref,chart=chart,
                boundaries=wires,native_area_mm2=face.Area(),surface_type=face.geomType(),
                status='needs_review',manufacturing_approved=False,
                protection_definition='Distance measured on native target chart for developable surfaces; arbitrary surface requires piecewise error and process review. No silent plane projection.')

def edge_band(face,edge,width_mm=3.0):
    """Native sampled 3D distance field over target triangles.

    It measures Euclidean distance to a true edge in 3D, explicitly NOT a surface
    geodesic. Triangle distance intervals use a declared twice-chord patch-radius estimate; curved patch bounds require manufacturing review.
    """
    if not math.isfinite(width_mm) or width_mm<=0:raise NetError('invalid_feature_band')
    points,triangles=face.tessellate(min(width_mm/10,.25),.2)
    if len(triangles)>12000:raise NetError('paint_triangle_budget')
    pending=[[points[i] for i in ids] for ids in triangles];refined=[]
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    surf=BRepAdaptor_Surface(face.wrapped)
    while pending:
        vertices=pending.pop()
        lengths=[((vertices[a]-vertices[b]).Length,a,b,c) for a,b,c in [(0,1,2),(1,2,0),(2,0,1)]]
        length,a,b,c=max(lengths)
        if length>width_mm/2:
            uv=face.paramAt((vertices[a]+vertices[b])*0.5);p=surf.Value(*uv);mid=cq.Vector(p.X(),p.Y(),p.Z())
            pending.extend([[vertices[a],mid,vertices[c]],[mid,vertices[b],vertices[c]]])
            if len(pending)+len(refined)>24000:raise NetError('paint_triangle_budget')
        else:refined.append(vertices)
    rows=[]
    for vertices in refined:
        distances=[cq.Vertex.makeVertex(*p.toTuple()).distance(edge) for p in vertices]
        diameter=max((a-b).Length for a in vertices for b in vertices)
        lower=max(0.,min(distances)-2*diameter);upper=max(distances)+2*diameter
        state='protected' if upper<=width_mm else 'unprotected' if lower>width_mm else 'boundary_uncertain'
        rows.append(dict(world_mm=[list(p.toTuple()) for p in vertices],distance_interval_mm=[lower,upper],classification=state))
    return dict(width_mm=width_mm,metric='native_3d_edge_distance',triangles=rows,status='needs_review',
                reason='Geodesic/process definition needs engineer approval; uncertain triangles retained, never silently omitted.')

def feature_inventory(shape):
    """Actual inner-wire mouths and adjoining native surfaces, including depth."""
    faces=shape.Faces();features=[]
    for i,face in enumerate(faces):
        for j,wire in enumerate(face.innerWires()):
            adjacent=[]
            for k,other in enumerate(faces):
                if i==k:continue
                if any(a.isSame(b) for a in wire.Edges() for b in other.Edges()):adjacent.append(k)
            depths=[]
            if face.geomType()=='PLANE':
                plane=Plane(face)
                depths=[plane.gap(v.Center()) for k in adjacent for v in faces[k].Vertices()]
            features.append(dict(id=f'face-{i}/mouth-{j}',target_face=i,adjacent_faces=adjacent,
                adjacent_types=[faces[k].geomType() for k in adjacent],signed_depth_range_mm=[min(depths),max(depths)] if depths else None,
                candidate='recess_or_hole' if depths and min(depths)<-1e-6 else 'boss_or_interface' if depths and max(depths)>1e-6 else 'needs_classification',
                status='needs_review',automatic_process_approval=False))
    return features
