"""Analytic isometries in native OCCT UV; UV is never a planar projection."""
import math
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Surface
from .panels import NetError

class Developable:
    def __init__(self,face):
        self.face=face;self.kind=face.geomType()
        self.surface=BRepAdaptor_Surface(face.wrapped)
        self.bounds=list(face._uvBounds())
        if self.kind=='CYLINDER':
            self.radius=self.surface.Cylinder().Radius();self.sine=0.
        elif self.kind=='CONE':
            cone=self.surface.Cone();self.radius=cone.RefRadius();self.sine=math.sin(cone.SemiAngle())
            if abs(self.sine)<1e-12:raise NetError('degenerate_cone')
            radii=[self.radius+v*self.sine for v in self.bounds[2:]]
            if min(radii)<-1e-7:raise NetError('cone_crosses_apex')
        elif self.kind!='PLANE':
            raise NetError('use_piecewise_for_double_curvature')
        if not all(math.isfinite(x) for x in self.bounds):raise NetError('unbounded_surface')

    def flat(self,u,v):
        if not all(math.isfinite(x) for x in (u,v)):raise NetError('non_finite_uv')
        u0,_,_,_=self.bounds
        if self.kind=='PLANE':return [u,v]
        if self.kind=='CYLINDER':return [self.radius*(u-u0),v]
        rho=self.radius/self.sine+v;theta=(u-u0)*self.sine
        return [rho*math.cos(theta),rho*math.sin(theta)]

    def uv(self,xy):
        x,y=xy;u0,_,_,_=self.bounds
        if self.kind=='PLANE':return [x,y]
        if self.kind=='CYLINDER':return [x/self.radius+u0,y]
        sign=1 if self.sine>0 else -1
        theta=math.atan2(y*sign,x*sign)
        # Select only the unique angular branch inside the cut chart.
        candidates=[]
        for k in range(-2,3):
            u=(theta+2*math.pi*k)/self.sine+u0
            if self.bounds[0]-1e-8<=u<=self.bounds[1]+1e-8:candidates.append(u)
        if len(candidates)!=1:raise NetError('ambiguous_cone_chart')
        return [candidates[0],sign*math.hypot(x,y)-self.radius/self.sine]

    def world(self,u,v):
        p=self.surface.Value(u,v)
        return [p.X(),p.Y(),p.Z()]

    def report(self,cuts=()):
        u0,u1,v0,v1=self.bounds
        cuts=list(cuts)
        if len(cuts)>128 or any(not math.isfinite(u) or not u0<u<u1 for u in cuts) or len(set(cuts))!=len(cuts):
            raise NetError('invalid_user_surface_cuts')
        limits=[u0,*sorted(cuts),u1];pieces=[]
        for i,(a,b) in enumerate(zip(limits,limits[1:])):
            if self.kind=='CYLINDER':
                lengths=dict(bottom_arc_mm=self.radius*(b-a),top_arc_mm=self.radius*(b-a),generator_mm=v1-v0)
            elif self.kind=='CONE':
                lengths=dict(bottom_arc_mm=(self.radius+v0*self.sine)*(b-a),top_arc_mm=(self.radius+v1*self.sine)*(b-a),
                             generator_mm=v1-v0,sector_angle_rad=abs(self.sine)*(b-a),slant_radii_mm=[abs(self.radius/self.sine+v) for v in (v0,v1)])
            else:lengths=dict(u_mm=b-a,v_mm=v1-v0)
            error=0.
            for u in np.linspace(a+1e-9,b-1e-9,9):
                for v in np.linspace(v0,v1,5):
                    uv2=self.uv(self.flat(u,v))
                    error=max(error,math.dist(self.world(u,v),self.world(*uv2)))
            pieces.append(dict(key=f'surface-piece-{i}',uv_bounds=[a,b,v0,v1],lengths=lengths,maximum_foldback_error_mm=error))
        expected_area=(u1-u0)*(v1-v0)
        if self.kind=='CYLINDER':expected_area*=self.radius
        elif self.kind=='CONE':expected_area*=self.radius+(v0+v1)*self.sine/2
        trim_evidence=None
        if self.kind in ('CYLINDER','CONE'):
            from .surface_charts import partition
            _,native_pieces,trim_evidence=partition(self.face,cuts)
            expanded=[]
            for patch in native_pieces:
                original=next(p for p in pieces if p['uv_bounds'][:2]==patch['u_interval'])
                expanded.append(dict(original,key=f'surface-piece-{len(expanded)}',outer_loop=patch['loops'][0],holes=patch['loops'][1:],native_uv_loops=patch['uv_loops'],flat_area_mm2=patch['flat_area_mm2']))
            pieces=expanded
        rectangular=abs(expected_area-self.face.Area())<=max(1e-6,self.face.Area()*1e-9)
        return dict(trim_evidence=trim_evidence,rectangular_trim=rectangular,schema_version=1,algorithm_version='b13-developable-v1',mapping_type='isometric',surface_type=self.kind,
                    uv_bounds=self.bounds,pieces=pieces,user_cut_u=cuts,native_trim_required=True,
                    native_area_mm2=self.face.Area(),manufacturing_tolerance=None,
                    measurement='Exact native parameter isometry; cylinder L=R*dU; cone arc=(R+V*sin(alpha))*dU and slant=dV. Foldback checked separately.',
                    status='measured')

def drawing(report,source_ref,revision):
    """Exact boundaries for untrimmed cylindrical/conical charts; triangles for approximations."""
    from ..domain.validation import validate
    entities=[];offset=0.
    def add(kind,**kw):
        entities.append(dict(id=f'{revision}:surface:{len(entities)}',kind=kind,layer='CUT',source_refs=[source_ref],**kw))
    if report['mapping_type']=='isometric' and report.get('rectangular_trim'):
        for p in report['pieces']:
            length=p['lengths']
            if report['surface_type']=='CYLINDER':
                w=length['bottom_arc_mm'];h=length['generator_mm']
                add('polyline',points=[[offset,0],[offset+w,0],[offset+w,h],[offset,h]],closed=True);offset+=w+20
            elif report['surface_type']=='CONE':
                r0,r1=sorted(length['slant_radii_mm']);angle=length['sector_angle_rad']
                center=[offset+r1,r1]
                add('arc',center=center,radius_mm=r1,start_angle_rad=0.,end_angle_rad=angle,direction='ccw')
                if r0>1e-8:add('arc',center=center,radius_mm=r0,start_angle_rad=angle,end_angle_rad=0.,direction='cw')
                for theta in [0.,angle]:
                    add('line',start=[center[0]+r0*math.cos(theta),center[1]+r0*math.sin(theta)],end=[center[0]+r1*math.cos(theta),center[1]+r1*math.sin(theta)])
                offset+=2*r1+20
    elif report['mapping_type']=='isometric':
        for p in report['pieces']:
            for loop in [p['outer_loop'],*p['holes']]:add('polyline',points=[[x+offset,y] for x,y in loop['points']],closed=True)
            xs=[x for x,y in p['outer_loop']['points']];offset+=max(xs)-min(xs)+20
    elif report['mapping_type']=='piecewise':
        for t in report['triangles']:
            points=t['flat_vertices'];xs=[p[0] for p in points];ys=[p[1] for p in points]
            add('polyline',points=[[p[0]-min(xs)+offset,p[1]-min(ys)] for p in points],closed=True)
            offset+=max(xs)-min(xs)+5
    if not entities:return None
    doc=dict(schema_version=1,id=revision+':surface-drawing',revision_id=revision,units='mm',
             frame=dict(origin=[0,0,0],x_axis=[1,0,0],y_axis=[0,1,0],z_axis=[0,0,1],units='mm',handedness='right'),
             layers=[dict(name='CUT',color=7,line_type='CONTINUOUS')],entities=entities,source_links=[source_ref])
    validate('drawing',doc,'DrawingDocument');return doc
