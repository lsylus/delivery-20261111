import math,json
import cadquery as cq
import pytest
from shapely.geometry import Polygon
from helpers import fixture,ROOT
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.surface_charts import world
from thermal_drawings.blanket.developable import Developable,drawing
from thermal_drawings.domain.acceptance import usable

def native_case(name,kind,index=None):
 shape=cq.Shape.importBrep(str(ROOT/f'fixtures/real-derived/b13/{name}.brep'))
 p,m=fixture(shape=shape);matches=[x for x in m.faces if x[1].geomType()==kind]
 occ,face,ref=m.faces[index] if index is not None else max(matches,key=lambda x:x[1].Area())
 p.update(envelope_policy='native_surface_v1',included_faces=[ref]);p['allowance']['factors']=[1,1,1]
 return p,m,face,ref

@pytest.mark.parametrize('name,kind,index',[('motor','CYLINDER',43),('conical-support','CONE',0),('fuel-tank','SPHERE',0)])
def test_native_trim_net_tabs_points_readback(name,kind,index,tmp_path):
 p,m,face,ref=native_case(name,kind,index)
 cover=generate(p,m,'native',tmp_path);net=generate_net(cover,dict(connection_plan='connected_15mm_v1'),output=tmp_path)
 assert usable(net) and net['status']=='needs_review' and not net['diagnostics']
 assert len(net['panels'])==2 and len(net['overlaps'])==2
 assert all(s['kind']=='join' for s in net['seams'])
 assert net['foldback']['maximum_error_mm']<1e-6
 assert sum(len(x['holes']) for x in net['panels'])==len(face.innerWires())
 assert all(t['width_mm']==15 for t in net['overlaps'])
 if kind=='SPHERE':
  for tab in net['overlaps']:
   measure=tab['surface_width_measurement']
   assert measure['acceptance']=='pass' and measure['width_metric']=='native_shortest_great_circle_distance_to_meridian'
   assert max(abs(w-15) for w in measure['native_circle_widths_mm']+measure['native_cap_lengths_mm'])<1e-6
   assert measure['native_boundary_types']==['CIRCLE']*4 and measure['native_outside_receiving_area_mm2']<1e-6
   assert measure['native_pcurve_maximum_sampled_error_mm']<1e-6
   assert measure['native_area_mm2']==pytest.approx(measure['expected_area_mm2'],rel=1e-7)
   assert measure['chart_width_range_mm'][1]>20
  assert next(c for c in net['checks'] if c['id']=='native_spherical_overlap_width')['status']=='pass'
  assert all(x['surface_trim']['distortion']['maximum_sampled_relative_length_difference']>.1 for x in net['panels'])
 else:assert all(abs(t['surface_width_measurement']['minimum_mm']-15)<.001 for t in net['overlaps'])
 panel=net['panels'][0];uv=list(Polygon(panel['outer_loop']['points'],[h['points'] for h in panel['holes']]).representative_point().coords)[0]
 edited=generate_net(cover,net['settings'],point_command=dict(action='add',id='native-point',panel_key=panel['key'],uv_mm=list(uv)))
 point=edited['fixed_points'][0];assert math.dist(point['position3d'],world(panel['surface_mapping'],uv))<1e-8
 assert cq.Vertex.makeVertex(*point['position3d']).distance(face)<1e-6
 for panel in net['panels']:
  if panel['holes']:
   uv=list(Polygon(panel['holes'][0]['points']).representative_point().coords)[0]
   with pytest.raises(ValueError):generate_net(cover,net['settings'],point_command=dict(action='add',panel_key=panel['key'],uv_mm=list(uv)))
 for path in tmp_path.rglob('*.brep'):
  actual=cq.Shape.importBrep(str(path));assert actual.isValid(),path
 assert net['native_readback']

def test_radial_hole_bspline_reaches_drawing_and_native_trim(tmp_path):
 shape=cq.Solid.makeCylinder(30,70).cut(cq.Solid.makeCylinder(6,80,cq.Vector(-40,0,35),cq.Vector(1,0,0))).clean()
 p,m=fixture(shape=shape);occ,face,ref=max((x for x in m.faces if x[1].geomType()=='CYLINDER'),key=lambda x:x[1].Area())
 assert face.innerWires() and any(e.geomType()=='BSPLINE' for e in face.Edges())
 report=Developable(face).report([math.pi]);doc=drawing(report,ref,'radial')
 assert doc and any(e['kind']=='polyline' for e in doc['entities'])
 p.update(envelope_policy='native_surface_v1',included_faces=[ref]);p['allowance']['factors']=[1,1,1]
 cover=generate(p,m,'radial',tmp_path)
 assert usable(cover) and all(x['surface_trim']['evidence']['native_wires'] for x in cover['panels'])
 assert any('BSPLINE'==e['curve_type'] for p in cover['panels'] for e in p['surface_trim']['evidence']['native_edges'])


def test_only_native_circle_edges_become_cone_arcs(tmp_path):
 import copy
 from thermal_drawings.blanket.net_drawing import drawing as net_drawing
 p,m,_,_=native_case('conical-support','CONE',0)
 cover=generate(p,m,'arc-types',tmp_path);net=generate_net(cover,dict(connection_plan='connected_15mm_v1'))
 assert any(e['kind']=='arc' for e in net['drawing_document']['entities'])
 changed=copy.deepcopy(net)
 for panel in changed['panels']:
  for edge in panel['surface_trim']['evidence']['native_edges']:edge['curve_type']='BSPLINE'
 assert all(e['kind']!='arc' for e in net_drawing(changed)['entities'])


def test_corner_relief_cut_lines_form_complete_manufacturing_boundary(tmp_path):
 from shapely.geometry import LineString,shape as geometry
 from shapely.ops import unary_union
 from shapely.affinity import translate
 p,m,_,_=native_case('fuel-tank','SPHERE',0)
 cover=generate(p,m,'cut-contour',tmp_path);net=generate_net(cover,dict(connection_plan='connected_15mm_v1'))
 assert any(t['relief_mm'][0]>0 for t in net['overlaps'])
 drawn=unary_union([LineString([e['start'],e['end']]) for e in net['drawing_document']['entities'] if e['layer']=='CUT' and e['kind']=='line'])
 material=unary_union([translate(geometry(piece['material_domain']),*piece['layout']['translation_mm']) for piece in net['pieces']])
 assert material.boundary.difference(drawn.buffer(1e-7)).length<1e-6
 assert drawn.difference(material.boundary.buffer(1e-7)).length<1e-6
