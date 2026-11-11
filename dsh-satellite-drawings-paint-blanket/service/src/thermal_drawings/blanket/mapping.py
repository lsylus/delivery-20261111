"""Rigid piecewise maps. Layout translations/rotations never enter foldback."""
import numpy as np
from shapely.affinity import affine_transform
from .panels import world

def apply(transform, point):
    return (np.array(transform['rotation'])@np.array(point)+np.array(transform['translation'])).tolist()

def inverse(transform, point):
    return (np.array(transform['rotation']).T@(np.array(point)-np.array(transform['translation']))).tolist()

def polygon(transform, shape):
    r=transform['rotation'];t=transform['translation']
    return affine_transform(shape,[r[0][0],r[0][1],r[1][0],r[1][1],*t])

def align(source,target,reflection=False):
    a,b=map(np.array,source);c,d=map(np.array,target)
    u=(b-a)/np.linalg.norm(b-a);v=(d-c)/np.linalg.norm(d-c)
    U=np.column_stack([u,[-u[1],u[0]]]);V=np.column_stack([v,[-v[1],v[0]]])
    if reflection:V[:,1]*=-1
    r=V@U.T
    return dict(rotation=r.tolist(),translation=(c-r@a).tolist())

def position3d(mapped_panel, piece_point):
    return world(mapped_panel, inverse(mapped_panel['transform'],piece_point))

def foldback(net):
    panels={p['key']:p for p in net['panels']};errors=[];vertices={}
    for p in panels.values():
        actual=[position3d(p,pt) for pt in p['net_outer']]
        expected=[world(p,pt) for pt in p['outer_loop']['points']]
        errors.extend(np.linalg.norm(np.array(actual)-np.array(expected),axis=1).tolist())
        for sample in p.get('surface_trim',{}).get('native_boundary_samples',[]):
            errors.append(float(np.linalg.norm(np.array(position3d(p,apply(p['transform'],sample['flat_mm'])))-np.array(sample['world_mm']))))
        vertices[p['key']]=actual
        for loop,orig in zip(p['net_holes'],p['holes'],strict=True):
            errors.extend(np.linalg.norm(np.array([position3d(p,x) for x in loop])-np.array([world(p,x) for x in orig['points']]),axis=1).tolist())
    for seam in net['seams']:
        a,b=(net['edges'][seam[k]] for k in ('edge_a','edge_b'))
        x=[position3d(panels[a['panel']],apply(panels[a['panel']]['transform'],pt)) for pt in a['uv']]
        y=[position3d(panels[b['panel']],apply(panels[b['panel']]['transform'],pt)) for pt in b['uv']]
        if seam['pair_orientation']=='opposite':y.reverse()
        errors.extend(np.linalg.norm(np.array(x)-np.array(y),axis=1).tolist())
    maximum=max(errors,default=0.)
    return dict(status='pass' if maximum<=1e-6 else 'fail',maximum_error_mm=maximum,vertices=vertices)
