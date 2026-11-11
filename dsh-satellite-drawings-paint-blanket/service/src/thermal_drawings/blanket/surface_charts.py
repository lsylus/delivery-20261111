"""Native trimmed surface charts, retained pcurves and explicit numerical errors."""
import math
import numpy as np
import cadquery as cq
from shapely.geometry import Polygon,box
from shapely.geometry.polygon import orient
from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve2d
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.TopAbs import TopAbs_REVERSED
from .panels import NetError
from ..paint.selection import polygons,loops

def descriptor(face):
    s=BRepAdaptor_Surface(face.wrapped);kind=face.geomType()
    obj=s.Cylinder() if kind=='CYLINDER' else s.Cone() if kind=='CONE' else s.Sphere() if kind=='SPHERE' else s.Plane() if kind=='PLANE' else None
    if obj is None:raise NetError('surface_chart_requires_cylinder_cone_or_sphere')
    frame=obj.Position();vec=lambda p:[p.X(),p.Y(),p.Z()]
    angle=obj.SemiAngle() if kind=='CONE' else 0.
    return dict(kind=kind,mapping_type='isometric' if kind!='SPHERE' else 'approximate',origin=vec(frame.Location()),x_axis=vec(frame.XDirection()),y_axis=vec(frame.YDirection()),z_axis=vec(frame.Direction()),radius_mm=0. if kind=='PLANE' else obj.RefRadius() if kind=='CONE' else obj.Radius(),sine=math.sin(angle),cosine=math.cos(angle),uv_bounds=list(face._uvBounds()),u_origin=face._uvBounds()[0])

def flat(m,uv):
    u,v=uv;r=m['radius_mm'];theta=u-m['u_origin']
    if m['kind']=='PLANE':xy=[theta,v]
    elif m['kind']=='CYLINDER':xy=[r*theta,v]
    elif m.get('chart_kind')=='gnomonic':
        if math.sin(v)<=0:raise NetError('gnomonic_chart_outside_front_hemisphere')
        xy=[r*math.cos(v)*math.cos(u)/math.sin(v),r*math.cos(v)*math.sin(u)/math.sin(v)]
    elif m['kind']=='SPHERE':xy=[r*theta,r*v]
    else:
        rho=r/m['sine']+v;t=theta*m['sine'];xy=[rho*math.cos(t),rho*math.sin(t)]
    return [x+d for x,d in zip(xy,m.get('chart_offset_mm',[0.,0.]))]

def native_uv(m,xy):
    x,y=[x-d for x,d in zip(xy,m.get('chart_offset_mm',[0.,0.]))];r=m['radius_mm']
    if m['kind']=='PLANE':return [m['u_origin']+x,y]
    if m['kind']=='CYLINDER':return [m['u_origin']+x/r,y]
    if m.get('chart_kind')=='gnomonic':return [math.atan2(y,x),math.atan2(r,math.hypot(x,y))]
    if m['kind']=='SPHERE':return [m['u_origin']+x/r,y/r]
    sign=1 if m['sine']>0 else -1;angle=math.atan2(y*sign,x*sign);candidates=[]
    for k in range(-2,3):
        u=m['u_origin']+(angle+2*math.pi*k)/m['sine']
        if m['uv_bounds'][0]-1e-7<=u<=m['uv_bounds'][1]+1e-7:candidates.append(u)
    if len(candidates)!=1:raise NetError('ambiguous_native_chart_inverse')
    return [candidates[0],sign*math.hypot(x,y)-r/m['sine']]

def world_uv(m,uv):
    u,v=uv;r=m['radius_mm']
    if m['kind']=='PLANE':return (np.array(m['origin'])+u*np.array(m['x_axis'])+v*np.array(m['y_axis'])).tolist()
    radius=r+v*m['sine'] if m['kind']=='CONE' else r*math.cos(v) if m['kind']=='SPHERE' else r
    z=v*m['cosine'] if m['kind']=='CONE' else r*math.sin(v) if m['kind']=='SPHERE' else v
    return (np.array(m['origin'])+radius*math.cos(u)*np.array(m['x_axis'])+radius*math.sin(u)*np.array(m['y_axis'])+z*np.array(m['z_axis'])).tolist()

def world(m,xy):return world_uv(m,native_uv(m,xy))

def trim(face,chord_mm=.02):
    if not .001<=chord_mm<=.1:raise NetError('chart_sampling_range')
    m=descriptor(face);wires=[];edge_records=[];count=0;maximum=0.
    for wi,wire in enumerate([face.outerWire(),*face.innerWires()]):
        explorer=BRepTools_WireExplorer(wire.wrapped,face.wrapped);uvloop=[]
        while explorer.More():
            edge=explorer.Current();curve=BRepAdaptor_Curve2d(edge,face.wrapped);a,b=curve.FirstParameter(),curve.LastParameter()
            if edge.Orientation()==TopAbs_REVERSED:a,b=b,a
            def uv(t):
                p=curve.Value(t);return [p.X(),p.Y()]
            samples=[]
            def sample(a,b,depth=0):
                nonlocal count,maximum
                ua,ub,uc=uv(a),uv(b),uv((a+b)/2);fa,fb,fc=map(lambda p:np.array(flat(m,p)),[ua,ub,uc]);wa,wb,wc=map(lambda p:np.array(world_uv(m,p)),[ua,ub,uc])
                err=max(np.linalg.norm(fc-(fa+fb)/2),np.linalg.norm(wc-(wa+wb)/2))
                if err>chord_mm and depth<20:sample(a,(a+b)/2,depth+1);sample((a+b)/2,b,depth+1);return
                if err>chord_mm:raise NetError('native_trim_sampling_budget')
                count+=1
                if count>60000:raise NetError('native_trim_point_budget')
                maximum=max(maximum,float(err));samples.append(ua)
            sample(a,b);samples.append(uv(b));uvloop.extend(samples[:-1])
            edge_records.append(dict(wire=wi,curve_type=cq.Edge(edge).geomType(),parameter_range=[a,b],native_uv=samples,flat_mm=[flat(m,p) for p in samples],world_mm=[world_uv(m,p) for p in samples]))
            explorer.Next()
        clean=[]
        for p in uvloop:
            if not clean or math.dist(flat(m,p),flat(m,clean[-1]))>1e-8:clean.append(p)
        if len(clean)>1 and math.dist(flat(m,clean[0]),flat(m,clean[-1]))<1e-8:clean.pop()
        wires.append(clean)
    domain=Polygon(wires[0],wires[1:])
    if not domain.is_valid or domain.area<=0:raise NetError('invalid_native_uv_trim')
    return m,domain,dict(native_wires=[dict(role='outer' if i==0 else 'inner',native_uv=w) for i,w in enumerate(wires)],native_edges=edge_records,sampling_chord_mm=chord_mm,maximum_sampled_midpoint_chord_mm=maximum,definition='Retained native pcurves with adaptive midpoint chord refinement; numerical representation bound is not a manufacturing tolerance or certified global bound')

def partition(face,cuts=(),chord_mm=.02):
    m,domain,evidence=trim(face,chord_mm);u0,u1,v0,v1=m['uv_bounds'];cuts=list(cuts)
    if len(set(cuts))!=len(cuts) or any(not math.isfinite(u) or not u0<u<u1 for u in cuts):raise NetError('invalid_user_surface_cuts')
    limits=[u0,*sorted(cuts),u1];result=[]
    for a,b in zip(limits,limits[1:]):
        for poly in polygons(domain.intersection(box(a,v0,b,v1))):
            rings=loops(poly);mapped=Polygon([flat(m,p) for p in rings[0]['points']],[[flat(m,p) for p in ring['points']] for ring in rings[1:]])
            if not mapped.is_valid:raise NetError('invalid_flattened_trim')
            mapped=mapped.simplify(1e-8,preserve_topology=True)
            flat_loops=loops(mapped)
            result.append(dict(loops=flat_loops,uv_loops=[dict(ring,points=[native_uv(m,p) for p in ring['points']]) for ring in flat_loops],u_interval=[a,b],flat_area_mm2=mapped.area))
    return m,result,evidence


def native_face(mapping,outer,holes=()):
    """Make an actual analytic-surface face from chart boundaries, with pcurves."""
    from OCP.gp import gp_Ax3,gp_Pnt,gp_Dir,gp_Pnt2d
    from OCP.Geom import Geom_CylindricalSurface,Geom_ConicalSurface,Geom_SphericalSurface,Geom_Plane
    from OCP.Geom2dAPI import Geom2dAPI_Interpolate
    from OCP.TColgp import TColgp_HArray1OfPnt2d
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeFace
    from OCP.BRepLib import BRepLib
    m=mapping;axis=gp_Ax3(gp_Pnt(*m['origin']),gp_Dir(*m['z_axis']),gp_Dir(*m['x_axis']))
    surface=Geom_Plane(axis) if m['kind']=='PLANE' else Geom_CylindricalSurface(axis,m['radius_mm']) if m['kind']=='CYLINDER' else Geom_ConicalSurface(axis,math.atan2(m['sine'],m['cosine']),m['radius_mm']) if m['kind']=='CONE' else Geom_SphericalSurface(axis,m['radius_mm'])
    wires=[]
    for i,ring in enumerate([outer,*holes]):
        uvs=[native_uv(m,p) for p in ring];area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(uvs,uvs[1:]+uvs[:1]))
        if (area>0)!=(i==0):ring=list(reversed(ring))
        maker=BRepBuilderAPI_MakeWire()
        for a,b in zip(ring,ring[1:]+ring[:1]):
            count=max(3,min(257,math.ceil(math.dist(a,b)/2)+1));array=TColgp_HArray1OfPnt2d(1,count)
            for j,t in enumerate(np.linspace(0,1,count),1):
                uv=native_uv(m,[(1-t)*a[k]+t*b[k] for k in range(2)]);array.SetValue(j,gp_Pnt2d(*uv))
            curve=Geom2dAPI_Interpolate(array,False,1e-8);curve.Perform()
            if not curve.IsDone():raise NetError('native_tab_pcurve_failed')
            maker.Add(BRepBuilderAPI_MakeEdge(curve.Curve(),surface).Edge())
        if not maker.IsDone():raise NetError('native_tab_wire_failed')
        wires.append(maker.Wire())
    maker=BRepBuilderAPI_MakeFace(surface,wires[0],True)
    for wire in wires[1:]:maker.Add(wire)
    if not maker.IsDone():raise NetError('native_tab_face_failed')
    face=cq.Face(maker.Face());BRepLib.BuildCurves3d_s(face.wrapped)
    if not face.isValid():raise NetError('invalid_native_tab')
    return face

def distortion(mapping,flat_loops):
    from shapely.geometry import Point
    if mapping.get('chart_kind')=='gnomonic':
        r=mapping['radius_mm'];offset=mapping.get('chart_offset_mm',[0.,0.]);rho=max(math.dist(p,offset) for ring in flat_loops for p in ring['points']);sec=math.sqrt(3)
        return dict(global_metric_bound=dict(length_stretch_minimum=1.,length_stretch_maximum=sec**2,relative_length_error_maximum=sec**2-1,area_stretch_maximum=sec**3,maximum_angle_rad=math.atan(math.sqrt(2)),applicability='Entire native cube-halfspace patch: absolute chart X and Y are at most R; independent of trim sampling'),definition='Gnomonic sphere chart: principal length stretches sec(theta) and sec(theta)^2; area stretch sec(theta)^3. Analytic bound, not approved material strain.',manufacturing_tolerance=None)
    material=Polygon(flat_loops[0]['points'],[x['points'] for x in flat_loops[1:]]);u0,u1,v0,v1=mapping['uv_bounds'];rows=[]
    for u in np.linspace(u0,u1,11)[1:-1]:
        for v in np.linspace(v0,v1,11)[1:-1]:
            for du,dv in [((u1-u0)/100,0),(0,(v1-v0)/100)]:
                a=[u,v];b=[u+du,v+dv];fa,fb=flat(mapping,a),flat(mapping,b)
                if not material.covers(Point(fa)) or not material.covers(Point(fb)):continue
                pts=[world_uv(mapping,[(1-t)*a[k]+t*b[k] for k in range(2)]) for t in np.linspace(0,1,33)]
                length=sum(math.dist(a,b) for a,b in zip(pts,pts[1:]));flat_length=math.dist(fa,fb)
                if length>1e-8:rows.append(abs(flat_length/length-1))
    bound={}
    if mapping['kind']=='SPHERE':
        pole=max(abs(v0),abs(v1));singular=pole>=math.pi/2-1e-12
        bound=dict(global_metric_bound=dict(status='unbounded_at_pole' if singular else 'finite',length_stretch_minimum=1.,length_stretch_maximum=None if singular else 1/math.cos(pole),relative_length_error_maximum=None if singular else 1/math.cos(pole)-1,applicability='Entire native UV latitude interval; equirectangular chart is singular at a pole'))
    return dict(**bound,maximum_sampled_relative_length_difference=max(rows,default=0.),samples=len(rows),definition='Interior native-UV grid; each path length approximated with 32 surface segments. Not a global strain bound or material approval.',manufacturing_tolerance=None)
