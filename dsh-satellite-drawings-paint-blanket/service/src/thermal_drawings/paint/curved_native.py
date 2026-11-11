"""Native normal-projected footprints on parallel analytic curved surfaces."""
import math
import numpy as np
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepOffsetAPI import BRepOffsetAPI_NormalProjection
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.ShapeFix import ShapeFix_Face
from OCP.TopAbs import TopAbs_REVERSED
from OCP.GeomAbs import GeomAbs_C2
from shapely.geometry import Polygon
from shapely.ops import unary_union
from ..blanket.surface_charts import descriptor,trim,flat
from .selection import PaintError

EPS=1e-7

def common(a,b):
    op=BRepAlgoAPI_Common(a.wrapped,b.wrapped);op.Build()
    if not op.IsDone():raise PaintError('native_footprint_common','Native footprint Common failed','failed')
    return cq.Shape.cast(op.Shape())

def support(face,wire=None):
    # ShapeFix/projection may mutate shared edge pcurves. Work on a private
    # face copy so constructing a mouth cannot change the source outer wire.
    original=[face.outerWire(),*face.innerWires()];index=next((i for i,w in enumerate(original) if wire is not None and w.isSame(wire)),0)
    face=face.copy();location=face.location();face=face.located(cq.Location());wire=[face.outerWire(),*face.innerWires()][index]
    from OCP.BRep import BRep_Tool
    surface=BRep_Tool.Surface_s(face.wrapped)
    maker=BRepBuilderAPI_MakeFace(surface,(wire or face.outerWire()).wrapped,True)
    fix=ShapeFix_Face(maker.Face());fix.Perform();result=cq.Face(fix.Face())
    if not result.isValid():raise PaintError('native_support_invalid','Cannot construct exact support trim','failed')
    return result.moved(location)

def parallel_gap(target,other):
    """Constant signed normal gap for coaxial cylinder, cone or concentric sphere.

    Frame/radius comparisons are numerical identity guards, not contact tolerance.
    The threshold comparison is kept in the caller and never widened here.
    """
    if target.geomType()!=other.geomType() or target.geomType() not in ('CYLINDER','CONE','SPHERE'):return None
    a,b=descriptor(target),descriptor(other);delta=np.array(b['origin'])-a['origin'];z=np.array(a['z_axis'])
    orientation=lambda f:-1 if f.wrapped.Orientation()==TopAbs_REVERSED else 1
    if a['kind']=='SPHERE':
        if np.linalg.norm(delta)>EPS:return None
        gap=b['radius_mm']-a['radius_mm']
    else:
        if np.linalg.norm(np.cross(z,b['z_axis']))>1e-10 or np.dot(z,b['z_axis'])<0:return None
        axial=float(np.dot(delta,z))
        if np.linalg.norm(delta-axial*z)>EPS:return None
        if a['kind']=='CYLINDER':gap=b['radius_mm']-a['radius_mm']
        else:
            if abs(a['sine']-b['sine'])>1e-12:return None
            gap=(b['radius_mm']-a['radius_mm'])*a['cosine']-axial*a['sine']
    return dict(gap_mm=orientation(target)*gap,normal_dot=orientation(target)*orientation(other),gap_bound_mm=[orientation(target)*gap]*2,definition='Constant normal gap proved by concentric/coaxial analytic surface parameters; face trim is intersected separately')

def project(source,target,max_distance):
    """Project complete native wires, including holes; build real support BRep."""
    from OCP.BRep import BRep_Tool
    base=support(target);surface=BRep_Tool.Surface_s(base.wrapped);wires=[]
    # Project onto an extended analytic carrier before intersecting true trim.
    # Otherwise cone normal projections at an axial end can lose a wire edge.
    u0,u1,v0,v1=target._uvBounds();margin=2*max_distance+1
    if target.geomType()=='SPHERE':
        v0=max(-math.pi/2,v0-margin/descriptor(target)['radius_mm']);v1=min(math.pi/2,v1+margin/descriptor(target)['radius_mm'])
    else:v0-=margin;v1+=margin
    carrier=BRepBuilderAPI_MakeFace(surface,u0,u1,v0,v1,1e-7).Face()
    for wire in [source.outerWire(),*source.innerWires()]:
        op=BRepOffsetAPI_NormalProjection(carrier);op.SetLimit(False);op.SetMaxDistance(max_distance+1e-6);op.SetParams(1e-8,1e-9,GeomAbs_C2,14,1000);op.Add(wire.wrapped);op.Build()
        if not op.IsDone():raise PaintError('native_projection_failed','Native wire projection did not finish','failed')
        result=cq.Shape.cast(op.Projection());found=result.Wires()
        if not found and result.Edges():found=cq.Wire.combine(result.Edges(),tol=1e-7)
        if len(found)!=1 or not found[0].IsClosed():raise PaintError('native_projection_ambiguous','Projection must yield one closed wire per source boundary: '+str([len(found),len(result.Edges()),[w.IsClosed() for w in found]]))
        wires.append(found[0])
    maker=BRepBuilderAPI_MakeFace(surface,wires[0].wrapped,True)
    for wire in wires[1:]:maker.Add(wire.wrapped)
    fix=ShapeFix_Face(maker.Face());fix.Perform();face=cq.Face(fix.Face())
    if not face.isValid():raise PaintError('native_projection_invalid','Projected support footprint invalid','failed')
    return common(face,base)

def chart(shape,mapping):
    parts=[]
    for face in shape.Faces():
        _,domain,_=trim(face)
        rings=[list(domain.exterior.coords)[:-1],*[list(x.coords)[:-1] for x in domain.interiors]]
        # Projection preserves the support's analytic surface parameter frame.
        middle=(mapping['uv_bounds'][0]+mapping['uv_bounds'][1])/2
        shift=0. if mapping['kind']=='PLANE' else 2*math.pi*round((middle-sum(u for u,v in rings[0])/len(rings[0]))/(2*math.pi))
        parts.append(Polygon([flat(mapping,[u+shift,v]) for u,v in rings[0]],[[flat(mapping,[u+shift,v]) for u,v in ring] for ring in rings[1:]]))
    return unary_union(parts)
