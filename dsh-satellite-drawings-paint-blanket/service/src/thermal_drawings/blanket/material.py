"""Explicit shared root topology; never enlarge material with a tolerance buffer."""
import math
import numpy as np
from shapely.geometry import Polygon,LineString,shape
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
from .panels import NetError


def stitched_body(panel,tabs,edges):
    points=panel['net_outer'];nodes={i:[] for i in range(len(points))}
    for tab in tabs:
        if tab['owner_panel']!=panel['key']:continue
        edge=next(e for e in edges.values() if e['panel']==panel['key'] and e['id'] in tab['seam_id'].split('~'))
        index=int(edge['id'].rsplit('/e',1)[1]);a=np.array(points[index]);b=np.array(points[(index+1)%len(points)]);delta=b-a
        for q in tab['net_loop'][:2]:
            t=float(np.dot(np.array(q)-a,delta)/np.dot(delta,delta))
            # This is only roundoff at a root already constructed from this edge.
            # Reject real gaps instead of snapping arbitrary nearby material.
            error=float(np.linalg.norm(np.array(q)-(a+t*delta)))
            budget=128*np.finfo(float).eps*max(1.,np.linalg.norm(a),np.linalg.norm(b),np.linalg.norm(delta))
            parameter_budget=budget/max(np.linalg.norm(delta),1.)
            if error>budget or t<-parameter_budget or t>1+parameter_budget:raise NetError('tab_root_mapping_mismatch',[tab['id']])
            t=min(1.,max(0.,t))
            if 0<t<1:nodes[index].append((t,q))
    ring=[]
    for i,q in enumerate(points):
        ring.append(q)
        for _,node in sorted(nodes[i],key=lambda row:row[0]):
            if node!=ring[-1]:ring.append(node)
    return Polygon(ring,panel['net_holes'])


def cut_boundary_check(net,document):
    material=[]
    for piece in net['pieces']:
        p=shape(piece['material_domain']);layout=piece['layout']
        material.append(translate(rotate(p,layout['rotation_rad'],origin=(0,0),use_radians=True),*layout['translation_mm']))
    boundary=unary_union(material).boundary;lines=[]
    for e in document['entities']:
        if e['layer']!='CUT':continue
        if e['kind']=='line':lines.append(LineString([e['start'],e['end']]))
        elif e['kind']=='polyline':lines.append(LineString(e['points']+([e['points'][0]] if e.get('closed') else [])))
        elif e['kind']=='arc':
            # material_domain stores native trim chords. Compare the matching
            # arc end-point chords here; the document retains the exact ARC.
            c=e['center'];r=e['radius_mm']
            lines.append(LineString([[c[0]+r*math.cos(e[k]),c[1]+r*math.sin(e[k])] for k in ['start_angle_rad','end_angle_rad']]))
    cuts=unary_union(lines)
    # Buffers are measurement neighbourhoods only; no material is changed.
    missing=boundary.difference(cuts.buffer(1e-7)).length
    extra=cuts.difference(boundary.buffer(1e-7)).length
    if missing>1e-6 or extra>1e-6:raise NetError('incomplete_material_cut_boundary',location=[missing,extra])
    return dict(missing_cut_length_mm=missing,extra_cut_length_mm=extra)


def boundary_cuts(net,document):
    """CUT belongs to final connected material, never to internal tab/fold edges."""
    arcs=[e for e in document['entities'] if e['layer']=='CUT' and e['kind']=='arc']
    kept=[e for e in document['entities'] if e['layer']!='CUT'];rows=[]
    for piece in net['pieces']:
        layout=piece['layout'];poly=translate(rotate(shape(piece['material_domain']),layout['rotation_rad'],origin=(0,0),use_radians=True),*layout['translation_mm'])
        refs=[]
        for panel in net['panels']:
            if panel['piece_id']==piece['id']:
                for ref in panel['source_refs']:
                    if ref not in refs:refs.append(ref)
        for ring in [poly.exterior,*poly.interiors]:
            points=list(ring.coords)
            if net.get('feature_composite') and not arcs:
                rows.append(dict(id=net['revision_id']+':material-cut:'+str(len(rows)),kind='polyline',layer='CUT',source_refs=refs,points=[list(q) for q in points[:-1]],closed=True))
                continue
            for a,b in zip(points,points[1:]):
                if math.dist(a,b)<=1e-9:continue
                entity=None
                for arc in arcs:
                    c=arc['center'];r=arc['radius_mm']
                    ends=[[c[0]+r*math.cos(arc[k]),c[1]+r*math.sin(arc[k])] for k in ['start_angle_rad','end_angle_rad']]
                    if min(max(math.dist(a,ends[0]),math.dist(b,ends[1])),max(math.dist(a,ends[1]),math.dist(b,ends[0])))<1e-7:
                        entity=dict(arc);break
                if entity is None:entity=dict(kind='line',layer='CUT',source_refs=refs,start=list(a),end=list(b))
                entity['id']=net['revision_id']+':material-cut:'+str(len(rows));rows.append(entity)
    return dict(document,entities=kept+rows)
