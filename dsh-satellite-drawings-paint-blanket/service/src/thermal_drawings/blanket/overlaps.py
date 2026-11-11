"""Full-width single-owner tabs plus flat and folded material collision checks."""
import math
import json
import numpy as np
from shapely.geometry import Polygon,LineString,Point,mapping
from shapely.ops import unary_union
from .panels import domain,AREA_TOL,LENGTH_TOL
from .mapping import apply,polygon,align


def _remove_roundoff_vertices(value):
    def clean(ring):
        result=[]
        for point in list(ring.coords)[:-1]:
            q=list(point)
            if result:
                budget=256*np.finfo(float).eps*max(1.,np.linalg.norm(result[-1]),np.linalg.norm(q))
                if math.dist(result[-1],q)<=budget:continue
            result.append(q)
        if len(result)>1:
            budget=256*np.finfo(float).eps*max(1.,np.linalg.norm(result[0]),np.linalg.norm(result[-1]))
            if math.dist(result[0],result[-1])<=budget:result.pop()
        return result
    cleaned=Polygon(clean(value.exterior),[clean(ring) for ring in value.interiors])
    area_budget=512*np.finfo(float).eps*max(1.,value.area)
    if not cleaned.is_valid or abs(cleaned.area-value.area)>area_budget:
        from .panels import NetError
        raise NetError('material_roundoff_cleanup_failed')
    return cleaned


def _planar_uv(panel, point):
    frame=panel['frame'];delta=np.array(point)-np.array(frame['origin'])
    return [float(np.dot(delta,frame['x_axis'])),float(np.dot(delta,frame['y_axis']))],abs(float(np.dot(delta,frame['z_axis'])))


def _feature_interface_tabs(net, panels, width):
    """Add cylinder-chart fan tabs without claiming a zero-strain circle fold."""
    from .panels import world
    tabs=[];interfaces=net.get('feature_composite',{}).get('interfaces',[])
    for interface in interfaces:
        if interface.get('native_curve_types')!=['CIRCLE'] or len(interface.get('panel_keys',[]))!=2:continue
        a,b=(panels.get(k) for k in interface['panel_keys'])
        if a is None or b is None:continue
        if a.get('surface_mapping',{}).get('kind')=='CYLINDER' and not b.get('surface_mapping'):owner,target=a,b
        elif b.get('surface_mapping',{}).get('kind')=='CYLINDER' and not a.get('surface_mapping'):owner,target=b,a
        else:continue
        matches=[];errors=[];target_domain=domain(target)
        for edge in net['edges'].values():
            if edge['panel']!=owner['key']:continue
            start,end=map(np.array,edge['uv']);delta=end-start;length=float(np.linalg.norm(delta))
            if length<=LENGTH_TOL or abs(delta[1])>1e-5:continue
            count=max(8 if math.dist(*edge['world'])<=LENGTH_TOL else 1,min(64,math.ceil(length/max(width,8.))))
            for index in range(count):
                r0=start+delta*index/count;r1=start+delta*(index+1)/count;mid=(r0+r1)/2
                q,residual=_planar_uv(target,world(owner,mid.tolist()))
                error=residual+target_domain.boundary.distance(Point(q));errors.append(error)
                if error<=.05:matches.append((edge,r0,r1))
        if not matches:
            interface['pattern_diagnostic']=dict(code='circular_boundary_not_matched',best_boundary_error_mm=min(errors,default=None))
            continue
        mapping_=owner['surface_mapping']
        created=[]
        for index,(edge,r0,r1) in enumerate(matches):
            delta=r1-r0;span=float(np.linalg.norm(delta));along=delta/span;outward=np.array([along[1],-along[0]]);inset=min(span*.18,width*.2)
            o0=r0+outward*width+along*inset;o1=r1+outward*width-along*inset
            owner_shape=Polygon([r0,r1,o1,o0])
            raw0,_=_planar_uv(target,world(owner,r0.tolist()));raw1,_=_planar_uv(target,world(owner,r1.tolist()))
            q0=np.array(target_domain.boundary.interpolate(target_domain.boundary.project(Point(raw0))).coords[0])
            q1=np.array(target_domain.boundary.interpolate(target_domain.boundary.project(Point(raw1))).coords[0])
            if np.linalg.norm(q1-q0)<=LENGTH_TOL:continue
            height=(r0[1]+r1[1])/2;center_world=np.array(mapping_['origin'])+height*np.array(mapping_['z_axis']);center,_=_planar_uv(target,center_world);center=np.array(center)
            radial0=(q0-center)/np.linalg.norm(q0-center);radial1=(q1-center)/np.linalg.norm(q1-center);receiving=[]
            for sign in (-1,1):
                p0=q0+sign*radial0*width;p1=q1+sign*radial1*width
                candidate=Polygon([q0,q1,p1,p0])
                if not candidate.is_valid:continue
                clipped=candidate.intersection(target_domain)
                if clipped.geom_type=='MultiPolygon':clipped=max(clipped.geoms,key=lambda shape:shape.area)
                if clipped.geom_type=='Polygon' and clipped.area>AREA_TOL:receiving.append((clipped.area,clipped))
            if not receiving:continue
            receiving_shape=max(receiving,key=lambda row:row[0])[1]
            flat=polygon(owner['transform'],owner_shape);seam_id=edge['id']+'~'+interface['id']
            tab=dict(id=f"tab:{interface['id']}:{index+1}",seam_id=seam_id,owner_panel=owner['key'],target_panel=target['key'],piece_id=owner['piece_id'],
                     width_mm=width,uv=[list(q) for q in owner_shape.exterior.coords[:-1]],net_loop=[list(q) for q in flat.exterior.coords[:-1]],
                     receiving_uv=[list(q) for q in receiving_shape.exterior.coords[:-1]],area_mm2=owner_shape.area,
                     surface_width_measurement=dict(pattern='segmented_fan_tabs_v1',interface_id=interface['id'],segment=index+1,segment_count=len(matches),requested_width_mm=width,acceptance='needs_material_sample',definition='Cylinder-chart tab depth; fold, slit coverage, wrinkling and material thickness require a physical sample'))
            tabs.append(tab);created.append(tab['id'])
        if created:
            interface.update(treatment='segmented_fan_tabs',overlap_status='generated_needs_material_sample',pattern_ids=created)
    return tabs

def strip(edge,width,outward=True):
    a,b=map(np.array,edge);u=(b-a)/np.linalg.norm(b-a)
    normal=np.array([u[1],-u[0]])*(1 if outward else -1)*width
    return Polygon([a,b,b+normal,a+normal])

def tab_shapes(owner,target,seam,panels,relief=0.):
    """Keep the requested width; explicit end relief avoids corner material clashes."""
    a,b=map(np.array,owner['uv']);c,d=map(np.array,target['uv']);length=np.linalg.norm(b-a)
    spherical=panels[target['panel']].get('surface_mapping',{}).get('kind')=='SPHERE'
    if spherical and not relief:raise ValueError('native_sphere_width_requires_explicit_corner_relief')
    if not relief and not spherical:return strip(owner['uv'],seam['width_mm']),strip(target['uv'],seam['width_mm'],False),[0.,0.]
    # Same relief at both ends is an explicit candidate, never a width reduction.
    start=end=float(relief) if length>2*relief else 0.
    for _ in range(64):
        if start+end>=length-1e-6:raise ValueError('no_full_width_tab_after_corner_relief')
        oe=[(a+(b-a)*start/length).tolist(),(b-(b-a)*end/length).tolist()]
        ts,te=(end,start) if seam['pair_orientation']=='opposite' else (start,end)
        target_edge=[(c+(d-c)*ts/length).tolist(),(d-(d-c)*te/length).tolist()]
        mapping_=panels[target['panel']].get('surface_mapping')
        if mapping_ and mapping_['kind']=='SPHERE':
            from .spherical_tabs import geometry
            try:receiving,_,_,_=geometry(mapping_,target_edge,seam['width_mm'])
            except ValueError:
                start+=max(.25,length/128);end+=max(.25,length/128);continue
            # Reflect the curved receiving boundary across the paired root into
            # owner chart space, retaining exactly the same cut-piece shape.
            td=(np.array(target_edge[1])-target_edge[0]);td=td/np.linalg.norm(td);tn=np.array([-td[1],td[0]])
            od=(np.array(oe[1])-oe[0]);od=od/np.linalg.norm(od);on=np.array([od[1],-od[0]])
            reverse=seam['pair_orientation']=='opposite';anchor=np.array(oe[1] if reverse else oe[0]);along=-od if reverse else od
            pts=[(anchor+along*np.dot(np.array(q)-target_edge[0],td)+on*np.dot(np.array(q)-target_edge[0],tn)).tolist() for q in list(receiving.exterior.coords)[:-1]]
            if reverse:pts=[pts[1],pts[0],*reversed(pts[2:])]
            # Shared root coordinates are authoritative. Re-evaluating the
            # receiving->owner transform introduces ULP-sized non-collinearity.
            pts[:2]=oe
            shape=Polygon(pts)
        else:shape=strip(oe,seam['width_mm']);receiving=strip(target_edge,seam['width_mm'],False)
        if receiving.difference(domain(panels[target['panel']])).area<=AREA_TOL and shape.intersection(domain(panels[owner['panel']])).area<=AREA_TOL:
            return shape,receiving,[start,end]
        # Bound the search by the edge length; failed candidates remain explicit.
        start+=max(.25,length/128);end+=max(.25,length/128)
    raise ValueError('no_full_width_tab_after_corner_relief')

def build_overlaps(net):
    ps={p['key']:p for p in net['panels']};tabs=[];diagnostics=net['diagnostics']
    def issue(code,refs,shape,candidates):
        diagnostics.append(dict(code=code,refs=refs,location=list(shape.representative_point().coords)[0],geometry=mapping(shape),coordinate_space='receiving_uv_mm' if code in ('tab_outside_receiving_material','folded_corner_collision') else 'owner_uv_mm' if code=='tab_intersects_owner' else 'piece_mm',candidates=candidates))
    for s in net['seams']:
        if s['kind']!='join':continue
        a,b=(net['edges'][s[k]] for k in ('edge_a','edge_b'))
        owner,target=(a,b) if a['panel']==s['overlap_owner_panel'] else (b,a)
        p,q=ps[owner['panel']],ps[target['panel']];width=s['width_mm']
        try:shape,receiving,relief=tab_shapes(owner,target,s,ps,15. if net['settings'].get('corner_relief_mode')=='native_boundary' else 0.)
        except ValueError:
            diagnostics.append(dict(code='no_full_width_tab_after_corner_relief',refs=[s['id']],location=None,candidates=[dict(action='change_owner',seam_id=s['id'])]));continue
        candidates=[dict(action='change_owner',seam_id=s['id'],panel_key=target['panel']),dict(action='change_width',seam_id=s['id'])]
        if shape.intersection(domain(p)).area>AREA_TOL:issue('tab_intersects_owner',[s['id'],p['id']],shape.intersection(domain(p)),candidates)
        outside=receiving.difference(domain(q))
        if outside.area>AREA_TOL:issue('tab_outside_receiving_material',[s['id'],q['id']],outside,candidates)
        flat=polygon(p['transform'],shape)
        # A fold carries authoritative endpoint coordinates from its parent.
        # Attach tabs to that same edge, rejecting anything beyond roundoff.
        index=int(owner['id'].rsplit('/e',1)[1]);a,b=map(np.array,owner['uv'])
        na=np.array(p['net_outer'][index]);nb=np.array(p['net_outer'][(index+1)%len(p['net_outer'])])
        coords=list(flat.exterior.coords)[:-1]
        for i,uv in enumerate(list(shape.exterior.coords)[:2]):
            t=float(np.dot(np.array(uv)-a,b-a)/np.dot(b-a,b-a))
            authoritative=(na if abs(t)<16*np.finfo(float).eps else nb if abs(t-1)<16*np.finfo(float).eps else na+t*(nb-na)).tolist()
            budget=512*np.finfo(float).eps*max(1.,np.linalg.norm(na),np.linalg.norm(nb),np.linalg.norm(nb-na))
            if np.linalg.norm(np.array(coords[i])-authoritative)>budget:
                from .panels import NetError
                raise NetError('tab_root_mapping_mismatch',[s['id']])
            coords[i]=authoritative
        flat=Polygon(coords)
        for other in ps.values():
            if other['key']==p['key'] or other['piece_id']!=p['piece_id']:continue
            overlap=flat.intersection(polygon(other['transform'],domain(other)))
            if overlap.area>AREA_TOL:issue('tab_hits_net_panel',[s['id'],other['id']],overlap,candidates)
        tabs.append(dict(id='tab:'+s['id'],seam_id=s['id'],owner_panel=p['key'],target_panel=q['key'],piece_id=p['piece_id'],
                         width_mm=width,uv=list(map(list,list(shape.exterior.coords)[:-1])),net_loop=list(map(list,list(flat.exterior.coords)[:-1])),
                         receiving_uv=list(map(list,list(receiving.exterior.coords)[:-1])),area_mm2=shape.area,relief_mm=relief))
    if net.get('feature_composite'):
        tabs.extend(_feature_interface_tabs(net,ps,net.get('settings',{}).get('interface_overlap_width_mm',15.)))
    # Sample receiving-surface paths across chart-width tabs. Sphere chart width
    # is explicitly distinct from physical width; this is not a geodesic proof.
    from .surface_charts import world
    for tab in tabs:
        mapping_=ps[tab['target_panel']].get('surface_mapping')
        if not mapping_:continue
        if mapping_['kind']=='SPHERE':
            from .spherical_tabs import geometry
            _,measurement,_,_=geometry(mapping_,tab['receiving_uv'][:2],tab['width_mm'])
            tab['surface_width_measurement']=measurement
            continue
        a,b,c,d=map(np.array,tab['receiving_uv']);widths=[]
        for t in np.linspace(0,1,9):
            start=(1-t)*a+t*b;end=(1-t)*d+t*c
            points=[world(mapping_,((1-q)*start+q*end).tolist()) for q in np.linspace(0,1,65)]
            widths.append(sum(math.dist(x,y) for x,y in zip(points,points[1:])))
        tab['surface_width_measurement']=dict(chart_width_mm=tab['width_mm'],sampled_path_widths_mm=widths,minimum_mm=min(widths),maximum_mm=max(widths),mapping_type=mapping_['mapping_type'],manufacturing_tolerance=None,acceptance='needs_review',definition='Nine receiving-surface paths, each sampled in 64 segments; not a shortest geodesic width or global bound')
    for i,a in enumerate(tabs):
        for b in tabs[i+1:]:
            for code,condition,pa,pb in [('flat_tab_collision',a['piece_id']==b['piece_id'],a['net_loop'],b['net_loop']),
                                         ('folded_corner_collision',a['target_panel']==b['target_panel'],a['receiving_uv'],b['receiving_uv'])]:
                pattern_a=a.get('surface_width_measurement',{});pattern_b=b.get('surface_width_measurement',{})
                fan_pair=(pattern_a.get('pattern')=='segmented_fan_tabs_v1'
                          and pattern_b.get('pattern')=='segmented_fan_tabs_v1')
                if code=='folded_corner_collision' and fan_pair:continue
                overlap=Polygon(pa).intersection(Polygon(pb))
                if condition and overlap.area>AREA_TOL:
                    seam_ids={s['id'] for s in net['seams']};candidates=[]
                    for tab in (a,b):
                        if tab['seam_id'] in seam_ids:candidates.append(dict(action='change_owner',seam_id=tab['seam_id']))
                    issue(code,[a['seam_id'],b['seam_id']],overlap,candidates)
    for diagnostic in diagnostics:
        for candidate in diagnostic['candidates']:
            if candidate.get('action')!='change_owner':continue
            seam=next((s for s in net['seams'] if s['id']==candidate['seam_id']),None)
            if seam is None:continue
            a,b=(net['edges'][seam[k]] for k in ('edge_a','edge_b'))
            owner,target=(b,a) if a['panel']==seam['overlap_owner_panel'] else (a,b)
            candidate.update(panel_key=owner['panel'],preview=dict(owner_uv_mm=list(map(list,list(strip(owner['uv'],seam['width_mm']).exterior.coords)[:-1])),receiving_panel_key=target['panel'],receiving_uv_mm=list(map(list,list(strip(target['uv'],seam['width_mm'],outward=False).exterior.coords)[:-1])),width_mm=seam['width_mm'],validation='candidate_not_applied'))
    cursor=0.
    explicit_layouts={x['piece_id'] for x in net['settings'].get('layouts',[])}
    for piece in net['pieces']:
        from .material import stitched_body
        bodies={p['key']:stitched_body(p,tabs,net['edges']) for p in ps.values() if p['piece_id']==piece['id']}
        for tab in [t for t in tabs if t['piece_id']==piece['id']]:
            root=LineString(tab['net_loop'][:2]);body=bodies[tab['owner_panel']];tab_shape=Polygon(tab['net_loop'])
            contact=body.boundary.intersection(tab_shape.boundary).intersection(root).length
            if root.length<=LENGTH_TOL or abs(contact-root.length)>LENGTH_TOL or body.intersection(tab_shape).area>AREA_TOL:
                seam_ids={s['id'] for s in net['seams']}
                candidates=[dict(action='change_owner',seam_id=tab['seam_id'])] if tab['seam_id'] in seam_ids else []
                issue('tab_root_not_attached',[tab['id'],tab['owner_panel']],root,candidates)
        material=unary_union([*bodies.values(),*[Polygon(t['net_loop']) for t in tabs if t['piece_id']==piece['id']]])
        if material.geom_type=='Polygon':material=_remove_roundoff_vertices(material)
        if material.geom_type!='Polygon' or not material.is_valid:
            issue('disconnected_piece_material',[piece['id']],material,[])
        piece['material_domain']=json.loads(json.dumps(mapping(material)))
        piece['material_area_mm2']=material.area
        xmin,ymin,xmax,ymax=material.bounds
        if piece['id'] not in explicit_layouts:piece['layout']['translation_mm']=[cursor-xmin,-ymin]
        cursor+=xmax-xmin+50.
    net['overlaps']=tabs
    net['areas']=dict(body_mm2=sum(domain(p).area for p in ps.values()),openings_mm2=sum(Polygon(h['points']).area for p in ps.values() for h in p['holes']),overlap_mm2=sum(t['area_mm2'] for t in tabs))
    return net
