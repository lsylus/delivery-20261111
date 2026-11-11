"""Native cubed-sphere patches with nonsingular gnomonic manufacturing charts."""
import math
import numpy as np
import cadquery as cq
from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_REVERSED
from shapely.geometry import Polygon
from .surface_charts import descriptor,flat
from .checks import boolean
from .panels import NetError
from ..paint.selection import loops
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.gp import gp_Pnt

def chart_point(m,point):
    q=np.array(point)-m['origin'];den=float(np.dot(q,m['z_axis']))
    if den<=0:raise NetError('gnomonic_chart_outside_front_hemisphere')
    return [m['radius_mm']*float(np.dot(q,m[k]))/den+d for k,d in zip(['x_axis','y_axis'],m.get('chart_offset_mm',[0.,0.]))]

def mapped_trim(face,m,chord):
    rings=[];records=[];maximum=0.;count=0
    for wi,wire in enumerate([face.outerWire(),*face.innerWires()]):
        scan=BRepTools_WireExplorer(wire.wrapped,face.wrapped);native_edges=[]
        while scan.More():native_edges.append(scan.Current());scan.Next()
        it=BRepTools_WireExplorer(wire.wrapped,face.wrapped);points=[]
        while it.More():
            edge=it.Current()
            if (BRep_Tool.IsClosed_s(edge,face.wrapped) and sum(edge.IsSame(e) for e in native_edges)>1) or BRep_Tool.Degenerated_s(edge):
                records.append(dict(wire=wi,curve_type=cq.Edge(edge).geomType(),topological_seam=True,flat_mm=[],world_mm=[],native_uv=[]));it.Next();continue
            curve=BRepAdaptor_Curve(edge);a,b=curve.FirstParameter(),curve.LastParameter()
            if edge.Orientation()==TopAbs_REVERSED:a,b=b,a
            samples=[]
            def at(t):
                p=curve.Value(float(t));xyz=[p.X(),p.Y(),p.Z()];return xyz,chart_point(m,xyz)
            def refine(a,b,depth=0):
                nonlocal maximum,count
                wa,pa=at(a);wb,pb=at(b);wc,pc=at((a+b)/2)
                error=max(np.linalg.norm(np.array(pc)-(np.array(pa)+pb)/2),np.linalg.norm(np.array(wc)-(np.array(wa)+wb)/2))
                if error>chord:
                    if depth>=20:raise NetError('sphere_atlas_trim_budget')
                    refine(a,(a+b)/2,depth+1);refine((a+b)/2,b,depth+1)
                else:
                    maximum=max(maximum,float(error));count+=1
                    if count>60000:raise NetError('sphere_atlas_trim_budget')
                    samples.append((wa,pa))
            refine(a,b);samples.append(at(b));points.extend(p for w,p in samples[:-1]);records.append(dict(wire=wi,curve_type=cq.Edge(edge).geomType(),parameter_range=[a,b],flat_mm=[p for w,p in samples],world_mm=[w for w,p in samples],native_uv=[]));it.Next()
        cleaned=[]
        for p in points:
            if not cleaned or math.dist(p,cleaned[-1])>1e-8:cleaned.append(p)
        if len(cleaned)>1 and math.dist(cleaned[-1],cleaned[0])<1e-8:cleaned.pop()
        rings.append(cleaned)
    poly=Polygon(rings[0],rings[1:]).simplify(1e-8,preserve_topology=True)
    if not poly.is_valid or poly.area<=1e-7:raise NetError('invalid_sphere_atlas_trim')
    return loops(poly),dict(native_wires=[dict(role='outer' if i==0 else 'inner',world_mm=[p for e in records if e['wire']==i for p in e['world_mm'][:-1]]) for i in range(len(rings))],native_edges=records,sampling_chord_mm=chord,maximum_sampled_midpoint_chord_mm=maximum,definition='Native 3D curve sampling in a gnomonic chart; midpoint chord estimate is separate from the analytic global metric bound')

def partition(face,rotation=(0,0,0),chord=.02):
    if face.geomType()!='SPHERE':raise NetError('sphere_atlas_requires_native_sphere')
    if len(rotation)!=3 or any(not math.isfinite(x) or abs(x)>180 for x in rotation):raise NetError('invalid_sphere_atlas_rotation')
    original=descriptor(face);origin=np.array(original['origin']);r=original['radius_mm'];basis=np.column_stack([original[k] for k in ['x_axis','y_axis','z_axis']])
    ax,ay,az=map(math.radians,rotation)
    rx=np.array([[1,0,0],[0,math.cos(ax),-math.sin(ax)],[0,math.sin(ax),math.cos(ax)]]);ry=np.array([[math.cos(ay),0,math.sin(ay)],[0,1,0],[-math.sin(ay),0,math.cos(ay)]]);rz=np.array([[math.cos(az),-math.sin(az),0],[math.sin(az),math.cos(az),0],[0,0,1]])
    basis=basis@rz@ry@rx;result=[]
    for index,(axis,sign) in enumerate([(0,1),(0,-1),(1,1),(1,-1),(2,1),(2,-1)]):
        z=sign*basis[:,axis];x=basis[:,(axis+1)%3];y=np.cross(z,x);actual=face
        for n in [z+x,z-x,z+y,z-y]:
            plane=cq.Face.makePlane(4*r,4*r,cq.Vector(*origin),cq.Vector(*n))
            half=BRepPrimAPI_MakeHalfSpace(plane.wrapped,gp_Pnt(*(origin+r*z))).Solid()
            actual=boolean(BRepAlgoAPI_Common,actual,cq.Shape.cast(half))
            if not actual.Faces():break
        actual=actual.clean()
        rebuild=None;parts=actual.Faces()
        if len(parts)>1:
            # A periodic source seam can split one physical cube patch after
            # STEP roundtrip. Remove only native edges shared by two faces and
            # rebuild on an equivalent spherical frame whose seam/poles lie
            # outside this cube patch. Preserve every true outer/inner edge.
            from OCP.Geom import Geom_SphericalSurface
            from OCP.gp import gp_Ax3,gp_Dir
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
            from OCP.ShapeFix import ShapeFix_Face
            all_edges=[e for part in parts for e in part.Edges()]
            boundary=[e for e in all_edges if sum(e.isSame(q) for q in all_edges)==1]
            wires=cq.Wire.combine(boundary,tol=1e-7)
            if len(boundary)<len(all_edges) and (len(wires)!=1 or not wires[0].IsClosed()):raise NetError('sphere_atlas_periodic_multiloop_requires_plan_change')
            if len(wires)==1 and wires[0].IsClosed():
                surface=Geom_SphericalSurface(gp_Ax3(gp_Pnt(*origin),gp_Dir(*y),gp_Dir(*z)),r)
                from .sphere_pcurves import attach
                wire=wires[0].copy();attach(wire.Edges(),surface,origin,r,z,y)
                maker=BRepBuilderAPI_MakeFace(surface,wire.wrapped,True);fix=ShapeFix_Face(maker.Face());fix.Perform();merged=cq.Face(fix.Face())
                if not merged.isValid():raise NetError('sphere_atlas_periodic_rebuild_invalid')
                # Verify native sets in both directions, never assume wire
                # reconstruction retained the intended side of the sphere.
                from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
                missing=merged
                for part in parts:missing=boolean(BRepAlgoAPI_Cut,missing,part)
                extra=sum(boolean(BRepAlgoAPI_Cut,part,merged).Area() for part in parts)
                if missing.Area()>1e-7 or extra>1e-7:raise NetError('sphere_atlas_periodic_rebuild_coverage')
                from OCP.BRepAdaptor import BRepAdaptor_Curve2d,BRepAdaptor_Surface
                from OCP.BRepGProp import BRepGProp
                from OCP.GProp import GProp_GProps
                maximum=0.;adaptor=BRepAdaptor_Surface(merged.wrapped)
                for edge in merged.Edges():
                    curve=BRepAdaptor_Curve(edge.wrapped);pc=BRepAdaptor_Curve2d(edge.wrapped,merged.wrapped)
                    for t in np.linspace(curve.FirstParameter(),curve.LastParameter(),1025):
                        uv=pc.Value(float(t));maximum=max(maximum,curve.Value(float(t)).Distance(adaptor.Value(uv.X(),uv.Y())))
                def area(f):
                    props=GProp_GProps();BRepGProp.SurfaceProperties_s(f.wrapped,props,1e-10,False);return props.Mass()
                difference=area(merged)-sum(area(f) for f in parts)
                if maximum>1e-6 or abs(difference)>1e-5:raise NetError('sphere_atlas_periodic_rebuild_precision: '+str([maximum,difference]))
                rebuild=dict(source_native_components=len(parts),pcurve_maximum_sampled_error_mm=maximum,adaptive_area_difference_mm2=difference,native_symmetric_difference_area_mm2=missing.Area()+extra)
                actual=merged
        for component,native in enumerate(actual.Faces()):
            if native.Area()<=1e-7:raise NetError('sphere_atlas_tiny_native_component_requires_plan_change')
            m=dict(original,chart_kind='gnomonic',x_axis=x.tolist(),y_axis=y.tolist(),z_axis=z.tolist(),u_origin=0.,uv_bounds=[-math.pi,math.pi,math.asin(1/math.sqrt(3)),math.pi/2])
            ls,evidence=mapped_trim(native,m,chord)
            if rebuild:evidence['periodic_seam_rebuild']=rebuild
            result.append(dict(mapping=m,actual=native,loops=ls,evidence=evidence,identity=dict(plan='cube_greatcircle_v1',rotation_deg=list(rotation),cube_face=index,component=component),flat_area_mm2=Polygon(ls[0]['points'],[h['points'] for h in ls[1:]]).area))
    if not result:raise NetError('empty_sphere_atlas')
    return result
