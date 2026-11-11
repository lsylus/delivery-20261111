"""Constant native geodesic width along supported spherical meridian seams."""
import math
import numpy as np
import cadquery as cq
from shapely.geometry import Polygon
from .surface_charts import world,native_uv,flat
from .panels import NetError

CHORD=.001

def geometry(mapping,root,width):
    m=mapping;r=m['radius_mm'];a,b=map(np.array,root);ua,ub=map(lambda p:native_uv(m,p),root)
    if m['kind']!='SPHERE' or width<=0 or width>=math.pi*r/2:raise NetError('invalid_native_sphere_width')
    origin=np.array(m['origin']);angle=width/r;atlas=m.get('chart_kind')=='gnomonic'
    if atlas:
        from .sphere_atlas import chart_point
        pa,pb=[(np.array(world(m,q))-origin)/r for q in root];arc=math.acos(float(np.clip(np.dot(pa,pb),-1,1)))
        if arc<1e-9 or arc>=math.pi-1e-9:raise NetError('ambiguous_sphere_greatcircle_root')
        normal=np.cross(pa,pb);normal/=np.linalg.norm(normal)
        delta=b-a;left=np.array([-delta[1],delta[0]])/np.linalg.norm(delta)
        probe=(np.array(world(m,((a+b)/2+left*.001).tolist()))-origin)/r
        if np.dot(normal,probe)<0:normal=-normal
        def point(t,fraction=1.):
            p=(math.sin((1-t)*arc)*pa+math.sin(t*arc)*pb)/math.sin(arc)
            return (origin+r*(math.cos(angle*fraction)*p+math.sin(angle*fraction)*normal)).tolist()
        def chart(p):return chart_point(m,p)
    else:
        if abs(ua[0]-ub[0])>1e-9:raise NetError('native_sphere_width_requires_meridional_seam')
        delta=b-a;direction=delta/np.linalg.norm(delta);sign=-direction[1]
        u=ua[0];normal=sign*(-math.sin(u)*np.array(m['x_axis'])+math.cos(u)*np.array(m['y_axis']));arc=abs(ub[1]-ua[1])
        def point(t,fraction=1.):
            v=(1-t)*ua[1]+t*ub[1];p=(np.array(world(m,flat(m,[u,v])))-origin)/r
            return (origin+r*(math.cos(angle*fraction)*p+math.sin(angle*fraction)*normal)).tolist()
        def chart(p):
            q=(np.array(p)-origin)/r;x=np.dot(q,m['x_axis']);y=np.dot(q,m['y_axis']);v=math.asin(max(-1.,min(1.,np.dot(q,m['z_axis']))));theta=math.atan2(y,x)
            choices=[theta+2*math.pi*k for k in range(-2,3) if m['uv_bounds'][0]-1e-7<=theta+2*math.pi*k<=m['uv_bounds'][1]+1e-7]
            if len(choices)!=1:raise NetError('native_sphere_tab_outside_chart')
            return flat(m,[choices[0],v])
    def sample(fn,start,end):
        values=[]
        def refine(a,b,depth=0):
            pa,pb,pm=map(lambda t:np.array(chart(fn(t))),[a,b,(a+b)/2]);error=float(np.linalg.norm(pm-(pa+pb)/2))
            if error>CHORD:
                if depth>=20:raise NetError('native_sphere_tab_sampling_budget')
                refine(a,(a+b)/2,depth+1);refine((a+b)/2,b,depth+1)
            else:values.append(pa.tolist())
        refine(start,end);values.append(chart(fn(end)));return values
    # Root is straight in the chart; other boundaries follow exact spherical arcs.
    points=[a.tolist(),b.tolist()]
    points+=sample(lambda t:point(1,t),0,1)[1:]
    points+=sample(lambda t:point(t),1,0)[1:]
    points+=sample(lambda t:point(0,t),1,0)[1:-1]
    polygon=Polygon(points)
    if not polygon.is_valid:raise NetError('invalid_native_sphere_tab')
    widths=[];offsets=[]
    for t in np.linspace(0,1,17):
        q=(np.array(point(t))-origin)/r
        widths.append(r*math.asin(max(-1.,min(1.,float(np.dot(q,normal))))))
        d=(b-a)/np.linalg.norm(b-a);q2=np.array(chart(point(t)))-a;offsets.append(float(abs(d[0]*q2[1]-d[1]*q2[0])))
    evidence=dict(requested_width_mm=width,root_arc_rad=arc,width_metric='native_shortest_great_circle_distance_to_seam' if atlas else 'native_shortest_great_circle_distance_to_meridian',sampled_geodesic_widths_mm=widths,minimum_mm=min(widths),maximum_mm=max(widths),chart_width_range_mm=[min(offsets),max(offsets)],flat_boundary_chord_mm=CHORD,acceptance='pass',definition='Exact spherical normal exponential offset q=cos(w/R)*p+R*sin(w/R)*n. Outer edge is a native small circle at signed plane distance R*sin(w/R); shortest great-circle distance to the meridian is w. End caps are native great-circle arcs of length w. Material strain approval remains separate.')
    return polygon,evidence,point,normal

def native_tab(mapping,root,width):
    from OCP.gp import gp_Ax3,gp_Pnt,gp_Dir
    from OCP.Geom import Geom_SphericalSurface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.ShapeFix import ShapeFix_Face
    polygon,evidence,point,normal=geometry(mapping,root,width)
    paths=[lambda t:point(t,0),lambda t:point(1,t),lambda t:point(1-t),lambda t:point(0,1-t)]
    edges=[cq.Edge.makeThreePointArc(cq.Vector(*fn(0)),cq.Vector(*fn(.5)),cq.Vector(*fn(1))) for fn in paths]
    m=mapping;u=native_uv(m,root[0])[0]
    # Put this local face away from the analytic surface's periodic seam.
    # Geometry is unchanged; both signed offsets project into one UV branch.
    local_z=np.array(m['z_axis']);x_axis=math.cos(u-math.pi/2)*np.array(m['x_axis'])+math.sin(u-math.pi/2)*np.array(m['y_axis'])
    if m.get('chart_kind')=='gnomonic':
        local_z=normal;x_axis=np.array(point(.5,0))-m['origin'];x_axis/=np.linalg.norm(x_axis)
    surface=Geom_SphericalSurface(gp_Ax3(gp_Pnt(*m['origin']),gp_Dir(*local_z),gp_Dir(*x_axis)),m['radius_mm'])
    from OCP.BRepAdaptor import BRepAdaptor_Curve,BRepAdaptor_Curve2d,BRepAdaptor_Surface
    from .sphere_pcurves import attach
    attach(edges,surface,m['origin'],m['radius_mm'],x_axis,local_z)
    wire=cq.Wire.assembleEdges(edges);maker=BRepBuilderAPI_MakeFace(surface,wire.wrapped,True)
    fix=ShapeFix_Face(maker.Face());fix.Perform();face=cq.Face(fix.Face())
    if not face.isValid():raise NetError('invalid_exact_spherical_tab')
    pcurve_error=0.;adaptor=BRepAdaptor_Surface(face.wrapped)
    for edge in face.Edges():
        c=BRepAdaptor_Curve(edge.wrapped);pc=BRepAdaptor_Curve2d(edge.wrapped,face.wrapped)
        for t in np.linspace(c.FirstParameter(),c.LastParameter(),257):
            uv=pc.Value(float(t));pcurve_error=max(pcurve_error,c.Value(float(t)).Distance(adaptor.Value(uv.X(),uv.Y())))
    if pcurve_error>1e-6:raise NetError('native_sphere_pcurve_readback_failed')
    # Independently evaluate OCCT's native CIRCLE edges, not the chart samples.
    outer=edges[2];observed=[];origin=np.array(m['origin']);r=m['radius_mm']
    for t in np.linspace(0,1,33):
        q=(np.array(outer.positionAt(float(t)).toTuple())-origin)/r
        observed.append(r*math.asin(max(-1.,min(1.,float(np.dot(q,normal))))))
    caps=[edges[i].Length() for i in (1,3)]
    if max(abs(x-width) for x in observed+caps)>1e-6:raise NetError('native_spherical_width_readback_failed')
    expected_area=r*r*math.sin(width/r)*evidence['root_arc_rad']
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props=GProp_GProps();integration_error=BRepGProp.SurfaceProperties_s(face.wrapped,props,1e-10,False);native_area=props.Mass()
    if abs(native_area-expected_area)>max(1e-5,expected_area*1e-7):raise NetError('native_spherical_tab_area_readback_failed: '+str([native_area,expected_area,integration_error]))
    evidence.update(native_pcurve_maximum_sampled_error_mm=pcurve_error,native_area_mm2=native_area,area_integration_relative_estimate=integration_error,expected_area_mm2=expected_area,native_circle_widths_mm=observed,native_cap_lengths_mm=caps,native_boundary_types=[e.geomType() for e in face.Edges()])
    return face,evidence
