"""B13 native measurements, independent numeric references and standalone plots."""
import json,os,sys,math,hashlib
from pathlib import Path
import cadquery as cq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from helpers import fixture,model_for
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.developable import Developable,drawing
from thermal_drawings.blanket.segmentation import piecewise
from thermal_drawings.blanket.exterior import offset_candidate
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.seams import adjacency
from thermal_drawings.paint.curved_targets import feature_inventory,inspect_target
OUT=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13')/'measurements'

def write(name,data):
 (OUT/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
def load(name):return cq.Shape.importBrep(str(ROOT/f'fixtures/real-derived/b13/{name}.brep'))
def triangles(shape,tolerance=1):
 points,indices=shape.tessellate(tolerance,.2)
 return [[points[i].toTuple() for i in ids] for ids in indices]
def equal_axes(ax,pts):
 v=np.array(pts).reshape(-1,3);lo=v.min(axis=0);hi=v.max(axis=0);c=(lo+hi)/2;radius=max(hi-lo)/2
 for setter,a in zip([ax.set_xlim,ax.set_ylim,ax.set_zlim],c):setter(a-radius,a+radius)
 ax.set_xlabel('X / mm');ax.set_ylabel('Y / mm');ax.set_zlabel('Z / mm')
def main():
 OUT.mkdir(parents=True,exist_ok=True);records={}
 manifest=json.loads((ROOT/'fixtures/manifests/complex_cases.json').read_text())
 assert hashlib.sha256(Path(manifest['source']).read_bytes()).hexdigest()==manifest['source_sha256']
 for case in manifest['cases']:
  data=(ROOT/case['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==case['sha256'] and len(data)==case['bytes']
 # This hand-derived source polygon is an independent STEP vertex/edge oracle,
 # not the construction algorithm's own volume result.
 polygon=[(75,145),(75,0),(425,0),(425,300),(375,300),(375,400),(225,400),(225,220),(0,220),(0,145)]
 area=abs(sum(x*y2-x2*y for (x,y),(x2,y2) in zip(polygon,polygon[1:]+polygon[:1])))/2
 assert area==113625
 for name,rotation in [('concave',False),('steps',True)]:
  source=load('computer-space');b=source.BoundingBox();local=source.translate((-b.xmin,-b.ymin,-b.zmin))
  if rotation:
   local=local.rotate((0,0,0),(0,1,0),-90);bb=local.BoundingBox();local=local.translate((-bb.xmin,-bb.ymin,-bb.zmin))
  params,model=fixture(shape=local);params['envelope_policy']='orthogonal_sections_v1';params['allowance']['factors']=[1.01]*3
  out=OUT/name;cover=generate(params,model,'measure-'+name,out);assert cover['status']=='needs_review' and cover['candidate_editable']
  assert abs(cover['baseline']['volume_mm3']-area*500)<1e-5
  _,seams=adjacency(cover['panels'])
  net=generate_net(cover,dict(connection_plan='connected_15mm_v1'),output=out)
  assert net['status']=='needs_review' and not net['diagnostics']
  records[name]=dict(source_case='computer-space',installation_orientation='rotated rigid coordinates' if rotation else 'original axes',
   expected_volume_mm3=area*500,baseline_volume_mm3=cover['baseline']['volume_mm3'],checks=cover['checks'],panels=len(cover['panels']),pieces=len(net['pieces']),foldback=net['foldback']['maximum_error_mm'])
 # Native closure preserves actual motor interfaces, rather than a global box.
 source=load('motor');base,cover,material,motor=offset_candidate(source,1.)
 assert all(c['status']=='pass' for k,c in motor['checks'].items() if k!='local_clearance')
 base.exportBrep(str(OUT/'motor-baseline.brep'));cover.exportBrep(str(OUT/'motor-cover.brep'));material.exportBrep(str(OUT/'motor-material.brep'));write('motor',motor);records['motor']=motor
 fig=plt.figure(figsize=(12,5))
 for i,(title,shape) in enumerate([('Actual motor with protruding interfaces',source),('1 mm native offset; bottom is evaluation closure',cover)],1):
  ax=fig.add_subplot(1,2,i,projection='3d');tris=triangles(shape);ax.add_collection3d(Poly3DCollection(tris,facecolor='#4d91b8',edgecolor='none',alpha=.75));equal_axes(ax,tris);ax.set_title(title,fontsize=10)
 fig.tight_layout();fig.savefig(OUT/'motor-envelope.png',dpi=150);plt.close(fig)
 for name,kind in [('fuel-tank','CYLINDER'),('conical-support','CONE')]:
  shape=load(name);face=max((f for f in shape.Faces() if f.geomType()==kind),key=lambda f:f.Area())
  chart=Developable(face);u0,u1,v0,v1=chart.bounds;report=chart.report([(u0+u1)/2])
  model=model_for(shape);ref=next(r for o,f,r in model.faces if f.isSame(face))
  doc=drawing(report,ref,'measure-'+name);assert doc is not None and report['rectangular_trim']
  report['drawing_document']=doc
  assert max(p['maximum_foldback_error_mm'] for p in report['pieces'])<1e-6
  records[name]=report;write(name,report)
 sphere=max((f for f in load('fuel-tank').Faces() if f.geomType()=='SPHERE'),key=lambda f:f.Area())
 variants=[]
 for resolution,angle in [(2.,.4),(.5,.2),(.15,.1)]:
  report=piecewise(sphere,resolution,angle);write('sphere-'+str(resolution),report)
  variants.append({k:report[k] for k in ['deflection_request_mm','triangle_count','maximum_chord_edge_error_mm','maximum_surface_chord_strain','maximum_sampled_deviation_mm','measurement','status']})
  if resolution==.5:
   tris=[t['world_vertices'] for t in report['triangles']];errors=np.array([t['maximum_sampled_deviation_mm'] for t in report['triangles']])
   fig=plt.figure(figsize=(10,6));ax=fig.add_subplot(111,projection='3d');collection=Poly3DCollection(tris,linewidths=.1)
   collection.set_array(errors);collection.set_cmap('viridis');ax.add_collection3d(collection);equal_axes(ax,tris)
   fig.colorbar(collection,ax=ax,shrink=.65,label='Sampled native-surface deviation / mm');ax.set_title('Actual fuel-tank end cap: piecewise chord triangles')
   fig.tight_layout();fig.savefig(OUT/'sphere-deviation.png',dpi=150);plt.close(fig)
 records['double_curvature']=dict(source_case='fuel-tank',candidates=variants,manufacturing_approval=None)
 # Actual mouths, slots, bosses and tilted native surfaces stay 3D.
 paint=[]
 for name in ['motor','mounting-plate','reaction-wheel','camera']:
  shape=load(name);features=feature_inventory(shape)
  paint.append(dict(case=name,features=features,process_approval=None))
 write('paint-features',paint);records['paint']=paint
 # Record exactly what remains a manufacturing decision, not a library choice.
 blockers=[dict(id='double-curvature-manufacturing',case='fuel-tank outer spherical end',measurements=variants,required='approved maximum sampled deviation/strain, seam density and confirmation whether sampled or certified global bounds are required'),
           dict(id='special-paint-process',cases=['motor','mounting-plate','reaction-wheel','camera'],required='approve native 3D edge-distance vs surface-geodesic 3mm protection, blind/counterbore/slot classification and boss coverage'),
           dict(id='openings-clearance',cases=['motor','launch-mechanism','computer-space'],required='approve technical selected installation opening and cover scope; measured candidates do not establish manufacturing tolerance')]
 write('acceptance',dict(schema_version=1,status='pass',full_acceptance=False,technical_measurements=records,manufacturing_status='blocked',blockers=blockers))
 print(json.dumps(dict(status='pass',sphere_candidates=variants,motor_ratio=motor['volume_ratio'],motor_outside=motor['checks']['containment']['outside_volume_mm3'])))
if __name__=='__main__':main()
