"""Unfold any supported planar adjacency forest, not a cross template."""
import copy
import numpy as np
from .panels import validate_panels,domain,NetError,AREA_TOL
from .seams import configure
from .mapping import apply,align,polygon

IDENTITY=dict(rotation=[[1.,0.],[0.,1.]],translation=[0.,0.])

def unfold(panels,settings=None):
    settings=copy.deepcopy(settings or {});ps=validate_panels(panels)
    base=settings.get('base_panel',next((k for k in ps if k=='z+'),next(iter(ps))))
    if base not in ps:raise NetError('unknown_base_panel',[base])
    es,seams=configure(panels,base,settings);graph={k:[] for k in ps}
    for s in seams:
        if s['kind']=='fold':
            a,b=es[s['edge_a']],es[s['edge_b']]
            graph[a['panel']].append((b['panel'],a,b,s));graph[b['panel']].append((a['panel'],b,a,s))
    assigned={};pieces=[];mapped=[]
    for root in [base,*[k for k in sorted(ps) if k!=base]]:
        if root in assigned:continue
        piece=dict(id=f'piece:{root}',panel_keys=[],layout=dict(translation_mm=[0.,0.],rotation_rad=0.))
        transforms={root:copy.deepcopy(IDENTITY)};parents={root:None};queue=[root];shared={root:{}}
        assigned[root]=piece['id']
        for parent in queue:
            piece['panel_keys'].append(parent)
            for child,ea,eb,seam in graph[parent]:
                if child==parents[parent]:continue
                if child in assigned:raise NetError('fold_cycle',[seam['id']],candidates=[dict(action='cut',seam_id=seam['id'])])
                parent_ring=[shared[parent].get(i,apply(transforms[parent],p)) for i,p in enumerate(ps[parent]['outer_loop']['points'])]
                edge_index=int(ea['id'].rsplit('/e',1)[1])
                target=[parent_ring[edge_index],parent_ring[(edge_index+1)%len(parent_ring)]]
                if seam['pair_orientation']=='opposite':target.reverse()
                transforms[child]=align(eb['uv'],target,reflection=seam['pair_orientation']=='same')
                child_index=int(eb['id'].rsplit('/e',1)[1]);shared[child]={}
                for index,uv,point in zip([child_index,(child_index+1)%len(ps[child]['outer_loop']['points'])],eb['uv'],target):
                    actual=apply(transforms[child],uv)
                    budget=512*np.finfo(float).eps*max(1.,np.linalg.norm(uv),np.linalg.norm(actual),np.linalg.norm(point))
                    if np.linalg.norm(np.array(actual)-point)>budget:raise NetError('fold_root_mapping_mismatch',[seam['id']])
                    shared[child][index]=list(point)
                assigned[child]=piece['id'];parents[child]=parent;queue.append(child)
        for k in queue:
            p=copy.deepcopy(ps[k]);t=transforms[k]
            p.update(key=k,piece_id=piece['id'],transform=t,front=bool(np.linalg.det(t['rotation'])>0),
                     net_outer=[shared[k].get(i,apply(t,x)) for i,x in enumerate(p['outer_loop']['points'])],net_holes=[[apply(t,x) for x in h['points']] for h in p['holes']])
            mapped.append(p)
        pieces.append(piece)
    diagnostics=[]
    for i,p in enumerate(mapped):
        for q in mapped[i+1:]:
            if p['piece_id']!=q['piece_id']:continue
            intersection=polygon(p['transform'],domain(p)).intersection(polygon(q['transform'],domain(q)))
            if intersection.area>AREA_TOL:
                diagnostics.append(dict(code='net_panel_overlap',refs=[p['id'],q['id']],location=list(intersection.representative_point().coords)[0],
                                        candidates=[dict(action='cut',seam_id=s['id']) for s in seams if s['kind']=='fold']))
    # Independent default packing: translation changes only sheet placement.
    cursor=0.
    for piece in pieces:
        pts=[x for p in mapped if p['piece_id']==piece['id'] for x in p['net_outer']]
        xs,ys=zip(*pts);piece['layout']['translation_mm']=[cursor-min(xs),-min(ys)];cursor+=max(xs)-min(xs)+50.
    for layout in settings.get('layouts',[]):
        match=next((p for p in pieces if p['id']==layout['piece_id']),None)
        if match is None:raise NetError('unknown_layout_piece',[layout['piece_id']])
        match['layout']=copy.deepcopy({k:v for k,v in layout.items() if k!='piece_id'})
    return dict(panels=mapped,pieces=pieces,edges=es,seams=seams,diagnostics=diagnostics,settings=settings)
