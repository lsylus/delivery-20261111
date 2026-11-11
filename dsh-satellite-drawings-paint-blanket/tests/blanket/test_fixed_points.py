import copy
import pytest
from thermal_drawings.blanket.fixed_points import edit,rebind
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.panels import NetError
from net_helpers import net,cover,cut_settings

def add(n,state=None,id_='anchor',key='z+',uv=(50,50)):
    return edit(n,state or n['point_state'],dict(action='add',id=id_,panel_key=key,uv_mm=list(uv)))

def test_add_move_delete_no_reuse_and_actual_mm_mapping():
    n=net();state=add(n);p=state['points'][0]
    assert p['uv_mm']==[50,50] and p['position3d']==pytest.approx([-2.5,-2.5,105])
    state=edit(n,state,dict(action='move',id='anchor',panel_key='z+',uv_mm=[80,60]))
    assert state['points'][0]['id']=='anchor' and state['points'][0]['uv_mm']==[80,60]
    state=edit(n,state,dict(action='delete',id='anchor'));assert not state['points']
    with pytest.raises(NetError,match='already_used'):add(n,state)

@pytest.mark.parametrize('uv',[(25,25),(-1,20),(106,20),(20,20),(20,25)])
def test_hole_exterior_and_boundary_points_rejected(uv):
    n=net(hole=True)
    with pytest.raises(NetError):add(n,uv=uv)

def test_duplicate_active_id_rejected():
    n=net();state=add(n)
    with pytest.raises(NetError,match='already_used'):add(n,state)
    state['points'].append(copy.deepcopy(state['points'][0]))
    with pytest.raises(NetError,match='duplicate'):rebind(n,state)

@pytest.mark.parametrize('spacing',[0,-1,float('nan'),1e-10,5e-324])
def test_spacing_positive_finite_and_bounded(spacing):
    n=net()
    with pytest.raises(NetError):edit(n,n['point_state'],dict(action='spacing',panel_key='z+',start_uv_mm=[10,10],end_uv_mm=[90,10],spacing_mm=spacing))

def test_spacing_atomic_if_a_point_hits_hole():
    n=net(hole=True)
    with pytest.raises(NetError):edit(n,n['point_state'],dict(action='spacing',panel_key='z+',start_uv_mm=[15,25],end_uv_mm=[45,25],spacing_mm=10))
    assert n['point_state']==dict(points=[],used_ids=[])

def test_spacing_then_cut_and_base_change_rebinds_same_id():
    c=cover();n=generate_net(c);state=edit(n,n['point_state'],dict(action='spacing',panel_key='z+',start_uv_mm=[10,10],end_uv_mm=[90,10],spacing_mm=20))
    assert len(state['points'])==5
    changed=generate_net(c,cut_settings(c,base='x+'),state)
    assert [p['id'] for p in changed['fixed_points']]==[p['id'] for p in state['points']]
    for old,new in zip(state['points'],changed['fixed_points']):
        assert old['position3d']==new['position3d'] and old['mapping_ref']!=new['mapping_ref'] and new['status']=='valid'

def test_tab_point_folds_onto_receiver_and_invalidates_when_tab_cut():
    c=cover();n=generate_net(c);tab=n['overlaps'][0]
    uv=[sum(p[i] for p in tab['uv'])/4 for i in range(2)]
    state=add(n,key=tab['owner_panel'],uv=uv);p=state['points'][0]
    receiver=next(p for p in c['panels'] if p['side']==tab['target_panel'])
    origin=receiver['frame']['origin'];normal=receiver['frame']['z_axis']
    assert sum((p['position3d'][i]-origin[i])*normal[i] for i in range(3))==pytest.approx(0)
    changed=generate_net(c,cut_settings(c),state)
    assert changed['status']=='failed' and changed['fixed_points'][0]['id']=='anchor' and changed['fixed_points'][0]['status']=='needs_reselection'


def test_internal_fold_is_material_and_becomes_boundary_after_cut():
    c=cover();n=generate_net(c);state=add(n,uv=(105,50))
    assert state['points'][0]['status']=='valid'
    changed=generate_net(c,cut_settings(c),state)
    assert changed['status']=='failed' and changed['fixed_points'][0]['status']=='needs_reselection'


def test_open_installation_bottom_material_boundary_rejected():
    n=net()
    with pytest.raises(NetError,match="point_on_material_boundary"):add(n,key="x+",uv=(50,0))
