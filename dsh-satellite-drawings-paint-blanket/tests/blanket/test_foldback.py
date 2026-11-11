import copy,math
import pytest
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.mapping import foldback
from net_helpers import cover,net,cut_settings

@pytest.mark.parametrize('dims,hole,multi',[( (100,100,100),False,False),((80,120,60),False,False),((80,120,60),True,True),((100,100,100),True,False)])
def test_foldback_vertices_holes_seams_match(dims,hole,multi):
    c=cover(dims,hole);n=generate_net(c,cut_settings(c) if multi else None)
    assert n['status']=='passed' and n['foldback']['status']=='pass' and n['foldback']['maximum_error_mm']<1e-6
    assert len(n['foldback']['vertices'])==5

def test_rigid_world_installation_rotation_and_translation():
    a=.73;frame=dict(origin=[250,-34,900],x_axis=[math.cos(a),math.sin(a),0],y_axis=[-math.sin(a),math.cos(a),0],z_axis=[0,0,1],units='mm',handedness='right')
    n=net(frame=frame,hole=True)
    assert n['status']=='passed' and n['foldback']['maximum_error_mm']<1e-6

def test_corrupted_net_vertex_fails_real_foldback():
    n=net();n['panels'][0]['net_outer'][0][0]+=.1
    assert foldback(n)['status']=='fail'

def test_corrupted_hole_vertex_fails_foldback():
    n=net(hole=True);p=next(p for p in n['panels'] if p['net_holes']);p['net_holes'][0][0][1]+=.5
    assert foldback(n)['status']=='fail'

def test_drawing_is_editable_entities_with_sources_and_same_revision():
    n=net(hole=True);d=n['drawing_document']
    assert d['revision_id']==n['revision_id'] and d['source_links']
    assert {'CUT','FOLD','OVERLAP','DIMENSION'}<={e['layer'] for e in d['entities']}
    assert all(e['source_refs'] for e in d['entities'])
    assert len([e for e in d['entities'] if e['layer']=='FOLD'])==4
