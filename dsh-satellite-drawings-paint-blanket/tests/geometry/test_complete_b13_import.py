import json
from pathlib import Path
import numpy as np
import cadquery as cq
import pytest
from geometry_core import load_model_snapshot
from geometry_core.tessellation import resolve_face
from geometry_core.hashing import file_sha256
from contracts import validate
from test_face_mesh_map import arrays
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('name,expected_faces',[('motor',44),('fuel-tank',6)])
def test_complete_occurrence_import_preserves_every_native_face(name,expected_faces,tmp_path):
 source=cq.Shape.importBrep(str(ROOT/f'fixtures/real-derived/b13/{name}.brep'))
 path=tmp_path/(name+'.step');cq.exporters.export(source,str(path));out=tmp_path/'snapshot'
 snapshot=load_model_snapshot(path,project_id='r2',model_id=name,model_revision=1,asset_id='native-full',output_dir=out)
 mapping=json.loads((out/'mesh-map.json').read_text());audit=json.loads((out/'tessellation-audit.json').read_text());validate('mesh-map',mapping)
 assert snapshot['units']=='mm' and snapshot['source_manifest']['load_status']=='complete'
 assert len(mapping['faces'])==audit['native_faces']==expected_faces and audit['dropped_native_faces']==0
 assert sum(len(f['collapsed_zero_area_triangles']) for f in audit['faces'])>0
 doc,get=arrays(out/'model.glb')
 for entry,fact in zip(mapping['faces'],audit['faces']):
  primitive=doc['meshes'][entry['mesh']]['primitives'][entry['primitive']];pos=get(primitive['attributes']['POSITION']);idx=get(primitive['indices']).reshape(-1,3)
  assert len(idx)==entry['triangle_count']==fact['emitted_triangles']>0
  assert fact['source_triangles']==fact['emitted_triangles']+len(fact['collapsed_zero_area_triangles'])
  for removed in fact['collapsed_zero_area_triangles']:
   assert removed['twice_area_mm2']==0 and len(set(map(tuple,removed['points_mm'])))<3
  assert all(np.linalg.norm(np.cross(b-a,c-a))>0 for a,b,c in pos[idx])
  assert fact['display_triangle_area_mm2']/fact['native_area_mm2']==pytest.approx(1,rel=.01)
  for i in [0,len(idx)-1]:assert resolve_face(mapping,model_ref=snapshot['model_ref'],glb_sha256=file_sha256(out/'model.glb'),node=entry['node'],mesh=entry['mesh'],primitive=entry['primitive'],triangle=i)==entry['face_ref']
 native=cq.Shape.importBrep(str(out/snapshot['definitions'][0]['shape_asset']))
 assert len(native.Faces())==expected_faces and native.Volume()==pytest.approx(source.Volume(),rel=1e-8)

@pytest.mark.parametrize('third',[(1.,1e-16,0.),(2.,0.,0.)])
def test_distinct_coordinate_degenerate_triangles_still_reject_import(third,tmp_path,monkeypatch):
 path=tmp_path/'box.step';cq.exporters.export(cq.Solid.makeBox(10,10,10),str(path));original=cq.Face.tessellate
 def with_bad_triangle(face,*args,**kwargs):
  points,triangles=original(face,*args,**kwargs);n=len(points)
  return [*points,cq.Vector(0,0,0),cq.Vector(1,0,0),cq.Vector(*third)],[*triangles,(n,n+1,n+2)]
 monkeypatch.setattr(cq.Face,'tessellate',with_bad_triangle)
 with pytest.raises(ValueError,match='degenerate tessellation triangle'):
  load_model_snapshot(path,project_id='negative',model_id='box',model_revision=1,asset_id='bad-display',output_dir=tmp_path/'snapshot')
 assert not (tmp_path/'snapshot/mesh-map.json').exists()
