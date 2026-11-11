"""Explicit, bounded connected seam proposals with full-width single-owner tabs."""
import copy
from shapely.geometry import Polygon
from .unfold import unfold
from .panels import domain,AREA_TOL,NetError
from .mapping import polygon
from .overlaps import tab_shapes
from .seams import adjacency


def automatic_planar_folds(panels, cuts=()):
    """Build a deterministic non-overlapping forest from planar adjacencies."""
    ps={p.get('key',p.get('side',p['id'])):p for p in panels};es,seams=adjacency(panels)
    cuts=set(cuts);folds=[]
    candidates=[]
    for seam in seams:
        a,b=(es[seam[k]]['panel'] for k in ('edge_a','edge_b'))
        if (seam['id'] in cuts or a==b or ps[a].get('surface_mapping')
                or ps[b].get('surface_mapping')):
            continue
        candidates.append(seam['id'])
    for seam_id in sorted(candidates):
        trial=[*folds,seam_id]
        try:net=unfold(panels,dict(fold_seam_ids=trial,cut_seam_ids=sorted(cuts)))
        except NetError:continue
        if not net['diagnostics']:folds=trial
    return folds


def propose(cover,intent=None):
    intent=copy.deepcopy(intent or {});es,seams=adjacency(cover['panels'])
    width=float(intent.pop('overlap_width_mm',15.))
    if not 0<width<=10000:raise NetError('invalid_overlap_width')
    if len(seams)>128:raise NetError('seam_plan_budget',candidates=[dict(action='reduce_patch_count')])
    if not seams:raise NetError('no_connected_seam_candidate')
    changes={s['id']:s for s in intent.get('seam_overrides',[])}
    if len(changes)!=len(intent.get('seam_overrides',[])) or not set(changes)<={s['id'] for s in seams}:raise NetError('unpaired_or_duplicate_seam')
    cuts=list(intent.get('cut_seam_ids',[]))
    cuts+= [k for k,v in changes.items() if v['kind']=='cut' and k not in cuts]
    required_folds=[k for k,v in changes.items() if v['kind']=='fold']
    if required_folds:
        intent['fold_seam_ids']=list(dict.fromkeys(intent.get('fold_seam_ids',[])+required_folds))
    curved=any(p.get('surface_mapping') for p in cover['panels'])
    folds=[intent['fold_seam_ids']] if 'fold_seam_ids' in intent else ([[]] if curved else [[s['id']] for s in seams if s['id'] not in cuts])
    changes={s['id']:s for s in intent.get('seam_overrides',[])}
    for fold in folds:
        if any(k in fold and v['kind']!='fold' or k in cuts and v['kind']!='cut' for k,v in changes.items()):continue
        settings=dict(fold_seam_ids=fold,cut_seam_ids=cuts,corner_relief_mode='native_boundary')
        if 'base_panel' in intent:settings['base_panel']=intent['base_panel']
        net=unfold(cover['panels'],settings)
        if net['diagnostics']:continue
        ps={p['key']:p for p in net['panels']};options={};invalid=False
        for seam in net['seams']:
            if seam['kind']!='join':continue
            a,b=(es[seam[k]] for k in ('edge_a','edge_b'));choices=[]
            for owner,target in [(a,b),(b,a)]:
                edit=dict(id=seam['id'],kind='join',overlap_owner_panel=owner['panel'],width_mm=width)
                if seam['id'] in changes and changes[seam['id']]!=edit:continue
                candidate_seam=dict(seam,width_mm=width)
                try:shape,receiving,relief=tab_shapes(owner,target,candidate_seam,ps,15.)
                except ValueError:continue
                flat=polygon(ps[owner['panel']]['transform'],shape);piece=ps[owner['panel']]['piece_id']
                if any(flat.intersection(polygon(p['transform'],domain(p))).area>AREA_TOL for p in ps.values() if p['key']!=owner['panel'] and p['piece_id']==piece):continue
                choices.append(dict(edit=edit,flat=flat,receiving=receiving,target=target['panel'],piece=piece))
            if not choices:invalid=True;break
            options[seam['id']]=choices
        if invalid or not options:continue
        ordered=sorted(options,key=lambda k:len(options[k]));selected={};visited=0
        def solve(i):
            nonlocal visited
            visited+=1
            if visited>20000:return False
            if i==len(ordered):return True
            key=ordered[i]
            for choice in options[key]:
                if any((choice['piece']==v['piece'] and choice['flat'].intersection(v['flat']).area>AREA_TOL) or (choice['target']==v['target'] and choice['receiving'].intersection(v['receiving']).area>AREA_TOL) for v in selected.values()):continue
                selected[key]=choice
                if solve(i+1):return True
                selected.pop(key)
            return False
        if solve(0):
            settings['seam_overrides']=[selected[k]['edit'] for k in sorted(selected)]+[v for v in changes.values() if v['kind']!='join']
            settings['layouts']=intent.get('layouts',[])
            return dict(settings=settings,folds=len(fold),joins=len(selected),cuts=len(cuts),width_mm=width,corner_relief_mode='native_boundary',search_nodes=visited,approval='candidate_not_applied',method='bounded_owner_constraints_with_explicit_corner_relief')
    raise NetError('no_feasible_connected_seam_plan',candidates=[dict(action='revise_patch_partition',reason='Requested full-width tabs or explicit seam intent do not fit; cuts and widths were not silently changed')])
