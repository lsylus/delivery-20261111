"""Editable DrawingDocument with separate cut, fold, overlap and fixing layers."""
import math
from .mapping import apply
from ..drawing.document import DrawingDocument

def _regular_circular_top(net, panel):
    """Recognize only the known regular-cylinder sampled top construction.

    This is not a short-edge filter: arbitrary planar faces keep every existing
    dimension. Diameter metadata must agree with a complete, uniformly ordered
    128-point circle before its chord annotations can be replaced.
    """
    envelope=net.get('regular_envelope',{})
    if envelope.get('shape')!='cylinder' or panel['key']!='z+' or panel.get('surface_mapping'):
        return None
    diameter=envelope.get('diameter_mm')
    points=panel['outer_loop']['points']
    if not isinstance(diameter,(int,float)) or not math.isfinite(diameter) or diameter<=0 or len(points)!=128:
        return None
    center=[sum(p[i] for p in points)/len(points) for i in range(2)]
    radius=diameter/2; tolerance=max(1e-7,radius*1e-9)
    if any(abs(math.dist(p,center)-radius)>tolerance for p in points):return None
    angles=[math.atan2(p[1]-center[1],p[0]-center[0]) for p in points]
    steps=[(b-a)%(2*math.pi) for a,b in zip(angles,angles[1:]+angles[:1])]
    if any(abs(step-2*math.pi/128)>1e-9 for step in steps):return None
    return center,radius


def drawing(net):
    ps={p['key']:p for p in net['panels']};pieces={p['id']:p for p in net['pieces']};entities=[]
    def sheet(panel,point):
        layout=pieces[panel['piece_id']]['layout'];angle=layout['rotation_rad'];c,s=math.cos(angle),math.sin(angle)
        return [c*point[0]-s*point[1]+layout['translation_mm'][0],s*point[0]+c*point[1]+layout['translation_mm'][1]]
    def add(kind,layer,refs,**data):
        entities.append(dict(id=f"{net['revision_id']}:net:{len(entities)}",kind=kind,layer=layer,source_refs=refs,**data))
    paired={eid:s for s in net['seams'] for eid in (s['edge_a'],s['edge_b'])}
    circular_tops={key:circle for key,p in ps.items() if (circle:=_regular_circular_top(net,p)) is not None}
    circumference_dimension_added=False
    height_dimension_added=False
    for edge in net['edges'].values():
        p=ps[edge['panel']];seam=paired.get(edge['id'])
        if seam and seam['kind']=='fold' and edge['id']!=seam['edge_a']:continue
        layer='FOLD' if seam and seam['kind']=='fold' else 'CUT'
        a,b=[sheet(p,apply(p['transform'],pt)) for pt in edge['uv']]
        # Joined owner edge is a tab bend/root; outer tab boundary is the cut.
        if seam and seam['kind']=='join' and p['key']==seam['overlap_owner_panel']:
            tab=next((t for t in net['overlaps'] if t['seam_id']==seam['id']),None)
            if tab:
                layer='OVERLAP'
                root=[sheet(p,apply(p['transform'],q)) for q in tab['uv'][:2]]
                # End relief exposes owner-body edge segments. These are cuts,
                # while only the actual shortened tab root is a bend line.
                for x,y in [(a,root[0]),(root[1],b)]:
                    if math.dist(x,y)>1e-8:add('line','CUT',p['source_refs'],start=x,end=y)
                a,b=root
        m=p.get('surface_mapping');uv=edge['uv'];native_circle=False
        if m and m['kind']=='CONE':
            from .surface_charts import native_uv
            ua,ub=[native_uv(m,xy) for xy in uv]
            # Equal endpoint radii alone cannot identify a circular trim: a
            # BSPLINE hole can have symmetric endpoints. Require a native
            # constant-V CIRCLE pcurve covering this precise angular interval.
            for original in p['surface_trim']['evidence']['native_edges']:
                samples=original['native_uv']
                if original['curve_type']=='CIRCLE' and max(v for u,v in samples)-min(v for u,v in samples)<1e-8 and all(abs(q[1]-samples[0][1])<1e-8 and min(u for u,v in samples)-1e-8<=q[0]<=max(u for u,v in samples)+1e-8 for q in [ua,ub]):
                    native_circle=True;break
        if native_circle:
            center=sheet(p,apply(p['transform'],[0,0]));angles=[math.atan2(q[1]-center[1],q[0]-center[0]) for q in (a,b)]
            delta=(angles[1]-angles[0]+math.pi)%(2*math.pi)-math.pi
            add('arc',layer,p['source_refs'],center=center,radius_mm=math.hypot(*uv[0]),start_angle_rad=angles[0],end_angle_rad=angles[1],direction='ccw' if delta>0 else 'cw')
        else:add('line',layer,p['source_refs'],start=a,end=b)
        regular_side=(net.get('regular_envelope',{}).get('shape')=='cylinder' and p['key']=='cylinder-side' and m and m['kind']=='CYLINDER')
        if not net.get('feature_composite') and not regular_side and p['key'] not in circular_tops and (not p.get('surface_mapping') or seam):add('dimension','DIMENSION',p['source_refs'],start=a,end=b,position=[(a[0]+b[0])/2+5,(a[1]+b[1])/2+5],text_override=None)
        if (not circumference_dimension_added and net.get('regular_envelope',{}).get('shape')=='cylinder'
                and p['key']=='cylinder-side' and m and m['kind']=='CYLINDER'
                and abs(uv[0][1]-uv[1][1])<1e-7
                and abs(abs(uv[0][0]-uv[1][0])-2*math.pi*m['radius_mm'])<1e-6):
            add('dimension','DIMENSION',p['source_refs'],start=a,end=b,position=[(a[0]+b[0])/2,(a[1]+b[1])/2-10],text_override=None)
            circumference_dimension_added=True
        if (regular_side and not height_dimension_added
                and abs(uv[0][0]-uv[1][0])<1e-7
                and abs(abs(uv[0][1]-uv[1][1])-(m['uv_bounds'][3]-m['uv_bounds'][2]))<1e-6):
            # Tab roots may be shortened by corner relief. Overall strip height
            # must use the original full chart edge, never that relieved root.
            start,end=[sheet(p,apply(p['transform'],q)) for q in uv]
            mid_x=sum(q[0] for q in p['outer_loop']['points'])/len(p['outer_loop']['points'])
            offset=10 if uv[0][0]>mid_x else -10
            position=sheet(p,apply(p['transform'],[uv[0][0]+offset,(uv[0][1]+uv[1][1])/2]))
            add('dimension','DIMENSION',p['source_refs'],start=start,end=end,position=position,text_override=None)
            height_dimension_added=True
    if net.get('feature_composite'):
        # Native trims remain complete cut polylines. Overall chart dimensions
        # describe each independent pattern without labelling sampled chords.
        for p in ps.values():
            xs,ys=zip(*p['outer_loop']['points']);x0,x1,y0,y1=min(xs),max(xs),min(ys),max(ys)
            for a,b,pos in [([x0,y0],[x1,y0],[(x0+x1)/2,y0-10]),([x0,y0],[x0,y1],[x0-10,(y0+y1)/2])]:
                a,b,pos=[sheet(p,apply(p['transform'],q)) for q in (a,b,pos)]
                add('dimension','DIMENSION',p['source_refs'],start=a,end=b,position=pos,text_override=None)
    for key,(center,radius) in circular_tops.items():
        p=ps[key]
        a,b=[sheet(p,apply(p['transform'],q)) for q in ([center[0]-radius,center[1]],[center[0]+radius,center[1]])]
        position=sheet(p,apply(p['transform'],[center[0],center[1]-radius-max(10.,radius*.25)]))
        add('dimension','DIMENSION',p['source_refs'],start=a,end=b,position=position,text_override=None)
    for p in ps.values():
        for hole in p['net_holes']:add('polyline','CUT',p['source_refs'],points=[sheet(p,x) for x in hole],closed=True)
    for tab in net['overlaps']:
        p=ps[tab['owner_panel']];points=[sheet(p,x) for x in tab['net_loop']]
        add('polyline','OVERLAP',p['source_refs'],points=points,closed=True)
        for a,b in zip(points[1:],points[2:]+points[:1]):add('line','CUT',p['source_refs'],start=a,end=b)
    for point in net['fixed_points']:
        if point['status']=='valid':
            p=ps[point['panel_key']];add('point','FIXING',p['source_refs'],position=sheet(p,point['net_uv_mm']))
    refs=[]
    for p in ps.values():
        for ref in p['source_refs']:
            if ref not in refs:refs.append(ref)
    document=dict(schema_version=1,id=net['revision_id']+':net-drawing',revision_id=net['revision_id'],units='mm',
                  frame=dict(origin=[0,0,0],x_axis=[1,0,0],y_axis=[0,1,0],z_axis=[0,0,1],units='mm',handedness='right'),
                  layers=[dict(name=name,color=i+1,line_type='DASHED' if name=='FOLD' else 'CONTINUOUS') for i,name in enumerate(['CUT','FOLD','OVERLAP','FIXING','DIMENSION'])],entities=entities,source_links=refs)
    if not net['diagnostics']:
        from .material import boundary_cuts
        document=boundary_cuts(net,document)
    document=DrawingDocument(document).to_dict()
    if not net['diagnostics']:
        from .material import cut_boundary_check
        cut_boundary_check(net,document)
    return document
