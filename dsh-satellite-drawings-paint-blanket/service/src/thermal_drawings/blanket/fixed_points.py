"""Persistent unique point identities in actual body/tab domains, never a UV box."""
import copy
import math
import uuid
from shapely.geometry import Point,Polygon,LineString,shape as geometry
from shapely.ops import unary_union
from .panels import domain,NetError,world,LENGTH_TOL
from .mapping import apply,align

MAX_POINTS=10000

def material(net,key):
    panel=next((p for p in net['panels'] if p['key']==key),None)
    if panel is None:raise NetError('unknown_point_panel',[key])
    return unary_union([domain(panel),*[Polygon(t['uv']) for t in net['overlaps'] if t['owner_panel']==key]])

def locate(net,key,uv):
    if len(uv)!=2 or any(not math.isfinite(x) for x in uv):raise NetError('invalid_point_coordinates',[key])
    shape=material(net,key);point=Point(uv)
    if not shape.covers(point):raise NetError('point_outside_material_or_in_hole',[key],uv)
    ps={p['key']:p for p in net['panels']};panel=ps[key]
    if shape.boundary.distance(point)<=LENGTH_TOL:
        on_fold=any(s['kind']=='fold' and any(net['edges'][s[e]]['panel']==key and LineString(net['edges'][s[e]]['uv']).distance(point)<=LENGTH_TOL for e in ('edge_a','edge_b')) for s in net['seams'])
        piece=next(p for p in net['pieces'] if p['id']==panel['piece_id'])
        if not on_fold or geometry(piece['material_domain']).boundary.distance(Point(apply(panel['transform'],uv)))<=LENGTH_TOL:
            raise NetError('point_on_material_boundary',[key],uv)
    if domain(panel).covers(point):return world(panel,uv),'body'
    tabs=[t for t in net['overlaps'] if t['owner_panel']==key and Polygon(t['uv']).covers(point)]
    if len(tabs)!=1:raise NetError('ambiguous_tab_mapping',[key],uv)
    tab=tabs[0];s=next(s for s in net['seams'] if s['id']==tab['seam_id'])
    a,b=(net['edges'][s[k]] for k in ('edge_a','edge_b'))
    owner,target=(a,b) if a['panel']==key else (b,a)
    points=target['uv'][::-1] if s['pair_orientation']=='opposite' else target['uv']
    transform=align(owner['uv'],points,reflection=s['pair_orientation']=='same')
    return world(ps[target['panel']],apply(transform,uv)),tab['id']

def rebind(net,state=None):
    state=copy.deepcopy(state or dict(points=[],used_ids=[]))
    ids=[p['id'] for p in state['points']]
    if len(ids)!=len(set(ids)) or len(state['used_ids'])!=len(set(state['used_ids'])) or not set(ids)<=set(state['used_ids']):raise NetError('duplicate_or_unreserved_point_id')
    if len(ids)>MAX_POINTS:raise NetError('point_budget')
    ps={p['key']:p for p in net['panels']}
    for p in state['points']:
        try:
            xyz,region=locate(net,p['panel_key'],p['uv_mm']);panel=ps[p['panel_key']]
            p.update(panel_id=panel['id'],position3d=xyz,mapping_ref=panel['mapping_ref'],net_uv_mm=apply(panel['transform'],p['uv_mm']),status='valid',region=region)
            p.pop('diagnostic',None)
        except NetError as error:
            p.update(status='needs_reselection',mapping_ref='invalidated:'+net['revision_id'],diagnostic=error.diagnostic)
    return state

def edit(net,state,command):
    result=copy.deepcopy(state);action=command['action']
    if action=='delete':
        match=next((p for p in result['points'] if p['id']==command['id']),None)
        if match is None:raise NetError('unknown_point_id',[command['id']])
        result['points'].remove(match)
    elif action=='move':
        match=next((p for p in result['points'] if p['id']==command['id']),None)
        if match is None:raise NetError('unknown_point_id',[command['id']])
        locate(net,command['panel_key'],command['uv_mm'])
        match.update(panel_key=command['panel_key'],uv_mm=command['uv_mm'])
    elif action in ('add','spacing'):
        key=command['panel_key']
        if action=='add':points=[command['uv_mm']];ids=[command.get('id') or 'fp:'+str(uuid.uuid4())]
        else:
            spacing=command['spacing_mm'];a,b=command['start_uv_mm'],command['end_uv_mm'];length=math.dist(a,b)
            if not math.isfinite(spacing) or spacing<=0 or not math.isfinite(length) or length<=0:raise NetError('invalid_spacing')
            quotient=length/spacing
            if not math.isfinite(quotient) or quotient>=MAX_POINTS:raise NetError('point_budget')
            n=math.floor(quotient)+1
            if n>MAX_POINTS or n+len(result['points'])>MAX_POINTS:raise NetError('point_budget')
            points=[[a[j]+(b[j]-a[j])*i*spacing/length for j in range(2)] for i in range(n)]
            ids=command.get('ids') or ['fp:'+str(uuid.uuid4()) for _ in points]
            if len(ids)!=len(points):raise NetError('spacing_id_count')
        if len(result['points'])+len(points)>MAX_POINTS:raise NetError('point_budget')
        for id_,uv in zip(ids,points):
            if id_ in result['used_ids']:raise NetError('point_id_already_used',[id_])
            locate(net,key,uv)
            result['used_ids'].append(id_);result['points'].append(dict(id=id_,panel_key=key,uv_mm=uv))
    else:raise NetError('unknown_point_action')
    return rebind(net,result)


def seed_feature_points(net,state,identity):
    """A few deterministic positioning markers, never holes or dense fasteners.

    IDs reserve initialisation even when the user subsequently deletes all
    markers. Safe-placement margins apply only to these initial suggestions.
    Existing user moves continue to use the ordinary material-domain validator.
    """
    state=copy.deepcopy(state or dict(points=[],used_ids=[]))
    if state['points']:return state
    from ..domain.validation import fingerprint
    # Reserve a deterministic initialization ID even if every panel is narrow.
    prefix='fp:auto:'+fingerprint(identity)[:20]
    if prefix+':initialized' in state['used_ids']:return state
    state['used_ids'].append(prefix+':initialized')
    ranked=sorted(net['panels'],key=lambda p:(-domain(p).area,p['key']))
    largest=domain(ranked[0]).area if ranked else 0.
    for panel in ranked:
        if len(state['points'])>=10:break
        body=domain(panel)
        if body.area<max(1000.,largest*.012):continue
        # Avoid body edges/openings and both owner and receiving overlap areas.
        margin=8.;safe=body.buffer(-margin)
        forbidden=[]
        for tab in net['overlaps']:
            if tab['owner_panel']==panel['key']:forbidden.append(Polygon(tab['uv']).buffer(margin))
            if tab['target_panel']==panel['key']:forbidden.append(Polygon(tab['receiving_uv']).buffer(margin))
        if forbidden:safe=safe.difference(unary_union(forbidden))
        if safe.is_empty:continue
        q=safe.representative_point();uv=list(q.coords)[0]
        id_=prefix+':'+panel['key']+':0'
        locate(net,panel['key'],uv)
        if id_ not in state['used_ids']:state['used_ids'].append(id_)
        state['points'].append(dict(id=id_,panel_key=panel['key'],uv_mm=list(uv)))
    return state
