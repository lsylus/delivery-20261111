import copy
from helpers import fixture,opening
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.net_pipeline import generate_net

def cover(dims=(100,100,100),hole=False,frame=None,revision='net-test'):
    p,m=fixture(dims,frame=frame)
    if hole:p['openings']=[opening()]
    return generate(p,m,revision)

def net(**kw):return generate_net(cover(**kw))

def cut_settings(c,folds=(),base='z+'):
    from thermal_drawings.blanket.seams import adjacency
    _,ss=adjacency(c['panels'])
    return dict(base_panel=base,fold_seam_ids=list(folds),cut_seam_ids=[s['id'] for s in ss if s['id'] not in folds])
