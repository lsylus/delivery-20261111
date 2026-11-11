"""Exact full-edge pairings, separate physical folds, cuts and joining seams."""
import math
from itertools import product
from .panels import edges, NetError, LENGTH_TOL,world,key

def adjacency(panels):
    es=edges(panels); paired=set();seams=[];ps={key(p):p for p in panels}
    values=list(es.values())
    # Endpoint buckets bound candidate search for native curved trim charts.
    # Neighbour cells preserve the existing full LENGTH_TOL pairing rule.
    cells={}
    cell=lambda p:tuple(math.floor(v/LENGTH_TOL) for v in p)
    for i,e in enumerate(values):
        for point in e['world']:cells.setdefault(cell(point),set()).add(i)
    for i,a in enumerate(values):
        c=cell(a['world'][0]);candidates=set()
        for offset in product((-1,0,1),repeat=3):
            candidates.update(cells.get(tuple(c[k]+offset[k] for k in range(3)),()))
        for j in sorted(k for k in candidates if k>i):
            b=values[j]
            # A complete cylindrical chart has two coincident longitudinal
            # boundary edges belonging to one physical strip. Retain that
            # joining seam so its overlap width remains editable.
            if a['panel']==b['panel'] and not (ps[a['panel']].get('surface_mapping',{}).get('kind')=='CYLINDER'):continue
            if min(math.dist(*a['world']),math.dist(*b['world']))<=LENGTH_TOL:continue
            same=all(math.dist(x,y)<=LENGTH_TOL for x,y in zip(a['world'],b['world']))
            opposite=all(math.dist(x,y)<=LENGTH_TOL for x,y in zip(a['world'],b['world'][::-1]))
            if not (same or opposite):continue
            # Equal endpoints do not identify complementary curved arcs.
            mids=lambda e:[world(ps[e['panel']],[(1-t)*e['uv'][0][i]+t*e['uv'][1][i] for i in range(2)]) for t in [.25,.5,.75]]
            ma,mb=mids(a),mids(b)
            if opposite:mb.reverse()
            if any(math.dist(x,y)>LENGTH_TOL for x,y in zip(ma,mb)):continue
            if a['id'] in paired or b['id'] in paired:raise NetError('nonmanifold_edge',[a['id'],b['id']])
            paired.update([a['id'],b['id']])
            seams.append(dict(id='~'.join(sorted([a['id'],b['id']])),edge_a=a['id'],edge_b=b['id'],
                              pair_orientation='same' if same else 'opposite',kind='join',overlap_owner_panel=a['panel'],width_mm=15.0))
    return es,sorted(seams,key=lambda s:s['id'])

def configure(panels,base,settings):
    es,seams=adjacency(panels);known={s['id'] for s in seams}
    explicit=settings.get('fold_seam_ids')
    cuts=settings.get('cut_seam_ids',[])
    if len(cuts)!=len(set(cuts)) or not set(cuts)<=known:raise NetError('unpaired_cut',cuts)
    if explicit is None:
        visited={base};explicit=[]
        # Choose a deterministic spanning forest. Never alter explicit user folds.
        queue=[base]
        for current in queue:
            for s in seams:
                a,b=es[s['edge_a']]['panel'],es[s['edge_b']]['panel']
                other=b if a==current else a if b==current else None
                if s['id'] not in cuts and other is not None and other not in visited:
                    explicit.append(s['id']);visited.add(other);queue.append(other)
    if len(explicit)!=len(set(explicit)) or not set(explicit)<=known or set(explicit)&set(cuts):
        raise NetError('invalid_fold_selection',explicit)
    overrides=settings.get('seam_overrides',[])
    if len({s['id'] for s in overrides})!=len(overrides) or any(s['id'] not in known for s in overrides):raise NetError('unpaired_or_duplicate_seam')
    for s in seams:
        if s['id'] in explicit:s.update(kind='fold',overlap_owner_panel=None,width_mm=0.)
        elif s['id'] in cuts:s.update(kind='cut',overlap_owner_panel=None,width_mm=0.)
        for edit in overrides:
            if edit['id']==s['id']:s.update({k:v for k,v in edit.items() if k!='id'})
        owners={es[s['edge_a']]['panel'],es[s['edge_b']]['panel']}
        if s['kind'] not in ('fold','cut','join'):raise NetError('invalid_seam_kind',[s['id']])
        if s['kind']!='join':
            if s['width_mm']!=0 or s['overlap_owner_panel'] is not None:raise NetError('nonjoin_overlap',[s['id']])
        elif s['overlap_owner_panel'] not in owners or not math.isfinite(s['width_mm']) or s['width_mm']<=0 or s['width_mm']>1e7:
            raise NetError('invalid_overlap_owner_or_width',[s['id']])
    return es,seams
