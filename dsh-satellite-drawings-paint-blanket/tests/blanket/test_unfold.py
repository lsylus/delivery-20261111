import copy
import math
import pytest
from shapely.geometry import Polygon,shape as geometry
from shapely.ops import unary_union
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.unfold import unfold
from thermal_drawings.blanket.panels import NetError
from net_helpers import cover,net,cut_settings

def test_real_five_105_cross_no_bottom():
    n=net();assert n['status']=='passed' and len(n['pieces'])==1 and len(n['panels'])==5
    shapes=[Polygon(p['net_outer']) for p in n['panels']]
    assert all(p.area==pytest.approx(105**2) for p in shapes)
    shape=unary_union(shapes)
    assert shape.area==55125 and shape.bounds==(-105.,-105.,210.,210.)
    assert all(p['key']!='z-' for p in n['panels'])
    assert len([s for s in n['seams'] if s['kind']=='fold'])==4
    material=geometry(n['pieces'][0]['material_domain'])
    assert material.is_valid and material.area==61425 and n['pieces'][0]['material_area_mm2']==61425

@pytest.mark.parametrize('dims',[(80,120,60),(160,40,200),(45,100,75)])
def test_rectangular_net_preserves_lengths(dims):
    c=cover(dims);n=generate_net(c)
    assert n['status']=='passed'
    expected=2*(dims[0]*dims[2]+dims[1]*dims[2])+dims[0]*dims[1]
    assert n['areas']['body_mm2']==pytest.approx(expected*1.05**2)
    for p in n['panels']:
        for i,a in enumerate(p['outer_loop']['points']):
            assert math.dist(a,p['outer_loop']['points'][(i+1)%4])==pytest.approx(math.dist(p['net_outer'][i],p['net_outer'][(i+1)%4]))

@pytest.mark.parametrize('base',['x-','x+','y-','y+','z+'])
def test_changed_base_and_multiple_pieces_are_not_cross_template(base):
    c=cover();settings=cut_settings(c,base=base);n=generate_net(c,settings)
    assert n['status']=='passed' and len(n['pieces'])==5 and not n['overlaps']
    assert n['pieces'][0]['panel_keys']==[base]

def test_cycle_is_rejected_with_explicit_cut_candidate():
    c=cover();n=net();folds=[s['id'] for s in n['seams']]
    with pytest.raises(NetError) as caught:unfold(c['panels'],dict(fold_seam_ids=folds))
    assert caught.value.diagnostic['code']=='fold_cycle' and caught.value.diagnostic['candidates']

def test_nonrectangular_planar_panel_keeps_true_outline_and_hole():
    c=cover();p=copy.deepcopy(c['panels'][-1]);p.pop('side');p['id']='L-panel'
    p['outer_loop']['points']=[[0,0],[80,0],[80,20],[20,20],[20,80],[0,80]]
    p['holes']=[dict(points=[[5,5],[5,10],[10,10],[10,5]],closed=True,orientation='cw')]
    c['panels']=[p];n=generate_net(c)
    assert n['status']=='passed' and n['areas']['body_mm2']==2775
    assert len(n['panels'][0]['net_outer'])==6 and len(n['panels'][0]['net_holes'])==1

def test_sheet_layout_is_not_engineering_geometry():
    c=cover();a=generate_net(c);b=generate_net(c,dict(layouts=[dict(piece_id=a['pieces'][0]['id'],translation_mm=[900,-350],rotation_rad=.73)]))
    for key in ['areas','foldback','overlaps','seams','panels','cover_checks']:assert a[key]==b[key]
    assert a['drawing_document']!=b['drawing_document']
    before=[math.dist(e['start'],e['end']) for e in a['drawing_document']['entities'] if e['kind']=='dimension']
    after=[math.dist(e['start'],e['end']) for e in b['drawing_document']['entities'] if e['kind']=='dimension']
    assert before==pytest.approx(after)
