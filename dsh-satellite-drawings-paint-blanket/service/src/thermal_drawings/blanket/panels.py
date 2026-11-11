"""Validated planar material domains; all engineering coordinates are millimetres."""
import math
import numpy as np
from shapely.geometry import Polygon

LENGTH_TOL = 1e-6
AREA_TOL = 1e-7

class NetError(ValueError):
    def __init__(self, code, refs=(), location=None, candidates=()):
        self.diagnostic = dict(code=code, refs=list(refs), location=location, candidates=list(candidates))
        super().__init__(code)

def world(panel, uv):
    if panel.get('surface_mapping'):
        from .surface_charts import world as surface_world
        return surface_world(panel['surface_mapping'],uv)
    f=panel['frame']
    return (np.array(f['origin']) + np.array(f['x_axis'])*uv[0] + np.array(f['y_axis'])*uv[1]).tolist()

def domain(panel):
    return Polygon(panel['outer_loop']['points'], [h['points'] for h in panel['holes']])

def key(panel):
    return panel.get('key', panel.get('side', panel['id']))

def validate_panels(panels):
    if not panels or len({key(p) for p in panels})!=len(panels) or len({p['id'] for p in panels})!=len(panels):
        raise NetError('duplicate_or_empty_panels')
    for p in panels:
        f=p['frame'];axes=np.array([f[k] for k in ('x_axis','y_axis','z_axis')],dtype=float)
        if not np.isfinite(axes).all() or not np.allclose(axes@axes.T,np.eye(3),atol=1e-9,rtol=0) or np.linalg.det(axes)<0:
            raise NetError('invalid_panel_frame',[p['id']])
        shape=domain(p)
        if not all(math.isfinite(v) for ring in [p['outer_loop'],*p['holes']] for pt in ring['points'] for v in pt) or not all(math.isfinite(v) for v in f['origin']):
            raise NetError('non_finite_panel',[p['id']])
        if not shape.is_valid or shape.area<=AREA_TOL or not shape.exterior.is_ccw or any(r.is_ccw for r in shape.interiors):
            raise NetError('invalid_material_domain',[p['id']])
    return {key(p):p for p in panels}

def edges(panels):
    result={}
    for p in panels:
        pts=p['outer_loop']['points']
        for i,(a,b) in enumerate(zip(pts,pts[1:]+pts[:1])):
            if math.dist(a,b)<=LENGTH_TOL: raise NetError('degenerate_edge',[p['id']])
            id_=f'{key(p)}/e{i}'
            result[id_]=dict(id=id_,panel=key(p),panel_id=p['id'],uv=[a,b],world=[world(p,a),world(p,b)])
    return result
