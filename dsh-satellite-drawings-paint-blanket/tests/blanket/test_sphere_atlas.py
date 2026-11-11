import json,math
import pytest
import cadquery as cq
from shapely.geometry import shape,Polygon
from test_native_surface_manufacturing import native_case
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.surface_charts import world,flat,native_uv
from thermal_drawings.blanket.material import cut_boundary_check

@pytest.mark.parametrize('roundtrip',[False,True])
@pytest.mark.parametrize('rotation',[[0,0,0],[0,0,23]])
def test_native_hemisphere_greatcircle_partition_tabs_and_restore(rotation,roundtrip,tmp_path):
 p,m,face,ref=native_case('fuel-tank','SPHERE',0)
 if roundtrip:
  from helpers import fixture
  path=tmp_path/'full-tank.step';cq.exporters.export(m.occurrences[0].shape,str(path));p,m=fixture(shape=cq.importers.importStep(str(path)).val())
  _,face,ref=max((row for row in m.faces if row[1].geomType()=='SPHERE'),key=lambda row:row[1].Area())
  p.update(envelope_policy='native_surface_v1',included_faces=[ref]);p['allowance']['factors']=[1,1,1]
 p['surface_options']=dict(partition_plan='cube_greatcircle_v1',rotation_deg=rotation,chart_chord_mm=.02)
 cover=generate(p,m,'atlas',tmp_path)
 assert len(cover['panels'])==5
 coverage=next(c for c in cover['checks'] if c['id']=='coverage')
 assert coverage['status']=='pass',coverage
 net=generate_net(cover,dict(connection_plan='connected_15mm_v1'),output=tmp_path)
 assert net['status']=='needs_review' and not net['diagnostics'],net['diagnostics']
 assert len(net['pieces'])==5 and len(net['overlaps'])==8
 assert all(shape(x['material_domain']).geom_type=='Polygon' for x in net['pieces'])
 for panel in net['panels']:
  bound=panel['surface_trim']['distortion']['global_metric_bound'];assert 1<bound['length_stretch_maximum']<=3.000001
  for xy in panel['outer_loop']['points']:
   assert math.dist(flat(panel['surface_mapping'],native_uv(panel['surface_mapping'],xy)),xy)<1e-7
   assert cq.Vertex.makeVertex(*world(panel['surface_mapping'],xy)).distance(face)<1e-6
 for tab in net['overlaps']:
  proof=tab['surface_width_measurement'];assert proof['width_metric']=='native_shortest_great_circle_distance_to_seam'
  assert max(abs(x-15) for x in proof['native_circle_widths_mm']+proof['native_cap_lengths_mm'])<1e-6
  assert proof['native_area_mm2']==pytest.approx(proof['expected_area_mm2'],rel=1e-7)
  assert proof['native_pcurve_maximum_sampled_error_mm']<1e-6 and proof['native_outside_receiving_area_mm2']<1e-6
 panel=net['panels'][0];xy=list(Polygon(panel['outer_loop']['points']).representative_point().coords)[0]
 edited=generate_net(cover,net['settings'],point_command=dict(action='add',id='atlas-point',panel_key=panel['key'],uv_mm=list(xy)))
 restored=generate_net(json.loads(json.dumps(cover)),json.loads(json.dumps(net['settings'])),point_state=edited['point_state'])
 assert restored['fixed_points']==edited['fixed_points'] and not restored['diagnostics']
 assert restored['foldback']['maximum_error_mm']<1e-6
