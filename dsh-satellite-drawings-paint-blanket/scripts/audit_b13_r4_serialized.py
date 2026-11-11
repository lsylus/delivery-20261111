"""Execution-side readback of saved R4 products; never independent approval.

No product envelope, net, overlap or paint builder is imported here.
"""
import os,json,math,hashlib,importlib.util,copy
from pathlib import Path
import cadquery as cq
import ezdxf
import numpy as np
from shapely.geometry import Polygon,Point,LineString
from OCP.BRepAdaptor import BRepAdaptor_Surface

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13/r4/browser-development')
reference=ROOT/'docs/evidence/B13/r1-review/independent_geometry.py'
assert hashlib.sha256(reference.read_bytes()).hexdigest()=='12f5cc4610127dc4d78685ee7019431816bf91298a425b6c37f61ac4f4fc7e9c'
spec=importlib.util.spec_from_file_location('independent_geometry',reference)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
def read(path):return json.loads(path.read_text())
def brep(path):
    s=cq.Shape.importBrep(str(path));assert s.isValid();return s
def close(a,b,tol=1e-6):assert abs(a-b)<tol,(a,b)
def face_for(ref,source):
    sig=ref['signature']
    found=[f for f in source.Faces() if f.geomType()==sig['type'] and abs(f.Area()-sig['area_mm2'])<1e-3 and math.dist(f.Center().toTuple(),sig['centroid_mm'])<1e-4]
    assert len(found)==1;return found[0]
def mapped(m,xy):
    x,y=np.array(xy)-m.get('chart_offset_mm',[0,0]);u=m['u_origin']+x/(m['radius_mm'] if m['kind']=='CYLINDER' else 1.)
    if m['kind']=='CYLINDER':a,b,z=m['radius_mm']*math.cos(u),m['radius_mm']*math.sin(u),y
    else:assert m['kind']=='PLANE';a,b,z=u,y,0
    return np.array(m['origin'])+a*np.array(m['x_axis'])+b*np.array(m['y_axis'])+z*np.array(m['z_axis'])

source=brep(ROOT/'fixtures/real-derived/b13/motor.brep');assert len(source.Faces())==44
base=out/'blanket-http';cover=read(base/'initial-cover.json')['blanket'];native=base/'initial-cover'
baseline=brep(native/'baseline.brep');solid=brep(native/'evaluation.brep');material=brep(native/'manufacturing.brep')
close(baseline.Volume(),5637234.35462044,1e-4);close(baseline.Volume(),cover['baseline']['volume_mm3'])
ratio=solid.Volume()/baseline.Volume();assert 1<ratio<1.2
outside=sum(s.Volume() for s in source.copy().cut(solid.copy()).Solids());assert outside<1e-6
bound=next(c for c in cover['checks'] if c['id']=='positive_clearance')['observed']
distances=[f.distance(source) for f in material.Faces()]
assert min(distances)>=min(p['lower_bound_mm'] for p in bound['panels'])-1e-6
initial=audit.load_net(base/'initial-net.json');restored=audit.load_net(base/'restored-net.json')
panels={p['key']:brep(native/Path(p['surface_ref']).name) for p in initial['panels']}
assert len(panels)==len(material.Faces())==34
folded=brep(base/'initial-native/folded-body.brep')
close(folded.Area(),material.Area())
body=[]
for f in folded.Faces():
    p=min(panels.values(),key=lambda p:math.dist(p.Center().toTuple(),f.Center().toTuple()))
    err=audit.cut_area(f.copy(),p.copy())+audit.cut_area(p.copy(),f.copy());assert err<1e-6;body.append(err)
tabs=brep(base/'initial-native/folded-tabs.brep').Faces();receiving=[]
panel_data={p['key']:p for p in initial['panels']}
for tab in initial['overlaps']:
    p=panel_data[tab['target_panel']];uv=tab['receiving_uv'];domain=Polygon(p['outer_loop']['points'],[h['points'] for h in p['holes']])
    root=LineString(uv[:2]);widths=[root.distance(Point(v)) for v in uv[2:]]
    assert tab['width_mm']==15 and max(abs(w-15) for w in widths)<1e-7
    outside_area=Polygon(uv).difference(domain).area;assert outside_area<1e-7
    frame=p['frame'];xyz=[np.array(frame['origin'])+x*np.array(frame['x_axis'])+y*np.array(frame['y_axis']) for x,y in uv]
    expected=cq.Face.makeFromWires(cq.Wire.makePolygon([cq.Vector(*v) for v in xyz],close=True))
    actual=min(tabs,key=lambda f:math.dist(f.Center().toTuple(),expected.Center().toTuple()));tabs.remove(actual)
    delta=audit.cut_area(actual.copy(),expected.copy())+audit.cut_area(expected.copy(),actual.copy());assert delta<1e-6
    receiving.append(dict(seam=tab['seam_id'],widths_mm=widths,outside_area_mm2=outside_area,native_symmetric_difference_mm2=delta))
assert not tabs
cuts={k:audit.drawing_cut_audit(n) for k,n in [('initial',initial),('restored',restored)]}
for filename in ['drawing.dxf','drawing.readback.dxf']:
    doc=ezdxf.readfile(base/'export'/filename);assert doc.units==4;entities=[]
    for e in doc.modelspace():
        if e.dxf.layer!='CUT':continue
        assert e.dxftype()=='LINE';entities.append(dict(kind='line',layer='CUT',start=list(e.dxf.start)[:2],end=list(e.dxf.end)[:2]))
    n=copy.deepcopy(restored);n['drawing_document']['entities']=entities;cuts[filename]=audit.drawing_cut_audit(n)
assert all(v['complete'] and all(p['components']==1 for p in v['piece_components']) for v in cuts.values())
seams={k:sum(s['kind']==k for s in initial['seams']) for k in ['fold','join','cut']}
assert seams==dict(fold=1,join=75,cut=0) and len(initial['pieces'])==33
assert seams['fold']>0 and seams['cut']==0 and seams['join']==len(initial['overlaps'])>0
assert len(initial['pieces'])==len(initial['panels'])-seams['fold']
blanket=dict(baseline_volume_mm3=baseline.Volume(),volume_ratio=ratio,uncovered_source_volume_mm3=outside,manufacturing_face_distances_mm=distances,folded_body_symmetric_difference_mm2=body,receiving_material=receiving,cuts=cuts,seams=seams,fixed_points=audit.fixed_point_audit(restored,panels))

result=dict(status='pass',method='Execution-side serialized BRep/NetResult/DXF and actual DWG reverse-conversion audit of browser-created products; no independent approval',blanket=blanket,independent_script_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),full_acceptance=False)
(out/'serialized-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print('R4 browser product serialized geometry, material and CUT readback: pass')
