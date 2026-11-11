"""The exact independently failed serialized owner/key, plus owner permutations."""
import copy,json,importlib.util,shutil
from pathlib import Path
import pytest
from shapely.geometry import shape,Polygon
from helpers import ROOT
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.material import stitched_body
from thermal_drawings.blanket.panels import NetError
BASE=ROOT/'docs/evidence/B13/r1/final-run-04/r1-http/fuel-tank-native'
spec=importlib.util.spec_from_file_location('independent_r1',ROOT/'docs/evidence/B13/r1-review/independent_geometry.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

@pytest.mark.parametrize('owners',[(0,0),(0,1),(1,0),(1,1)])
def test_exact_failed_key_owners_edit_restore_and_native_width(owners,tmp_path):
 cover=json.loads((BASE/'blanket-result.json').read_text());old=json.loads((BASE/'blanket-net.json').read_text());settings=copy.deepcopy(old['settings'])
 keys=[p['key'] for p in old['panels']]
 assert keys[0]=='surface-4e9985e93a3daf0504'
 for item,owner in zip(settings['seam_overrides'],owners):item['overlap_owner_panel']=keys[owner]
 for p in cover['panels']:
  dest=tmp_path/p['surface_ref'];dest.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(BASE/Path(p['surface_ref']).name,dest)
 initial=generate_net(cover,settings,output=tmp_path)
 panel=initial['panels'][0];uv=list(Polygon(panel['outer_loop']['points']).representative_point().coords)[0]
 edited=generate_net(cover,settings,point_command=dict(action='add',id='r2-anchor',panel_key=panel['key'],uv_mm=list(uv)))
 restored=generate_net(json.loads(json.dumps(cover)),json.loads(json.dumps(settings)),point_state=json.loads(json.dumps(edited['point_state'])))
 for net in [initial,edited,restored]:
  assert net['status']=='needs_review' and not net['diagnostics']
  assert all(shape(p['material_domain']).geom_type=='Polygon' for p in net['pieces'])
  cut=audit.drawing_cut_audit(net);assert cut['complete'] and all(x['components']==1 for x in cut['piece_components'])
 import cadquery as cq
 receiving=[cq.Shape.importBrep(str(tmp_path/p['surface_ref'])) for p in initial['panels']]
 for face in cq.Shape.importBrep(str(tmp_path/'folded-tabs.brep')).Faces():audit.audit_tab(face,receiving)
 assert restored['fixed_points']==edited['fixed_points']


def test_real_root_gap_is_rejected_not_buffered():
 cover=json.loads((BASE/'blanket-result.json').read_text());old=json.loads((BASE/'blanket-net.json').read_text());net=generate_net(cover,old['settings'])
 tab=copy.deepcopy(net['overlaps'][0]);panel=next(p for p in net['panels'] if p['key']==tab['owner_panel'])
 for q in tab['net_loop'][:2]:q[0]+=.001
 with pytest.raises(NetError,match='tab_root_mapping_mismatch'):stitched_body(panel,[tab],net['edges'])
