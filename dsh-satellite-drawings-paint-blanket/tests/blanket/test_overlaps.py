import copy
import pytest
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.seams import adjacency
from net_helpers import cover,net,cut_settings

def test_four_single_owner_15_tabs_no_fold_allowance():
    n=net();assert len(n['overlaps'])==4 and n['areas']['overlap_mm2']==6300
    assert len({t['seam_id'] for t in n['overlaps']})==4
    assert all(t['width_mm']==15 and t['area_mm2']==1575 for t in n['overlaps'])
    assert {t['seam_id'] for t in n['overlaps']}=={s['id'] for s in n['seams'] if s['kind']=='join'}

def test_switch_all_sides_keeps_enclosed_volume_and_net_dimensions():
    c=cover();a=generate_net(c);edits=[]
    for s in a['seams']:
        if s['kind']!='join':continue
        other=next(a['edges'][s[e]]['panel'] for e in ('edge_a','edge_b') if a['edges'][s[e]]['panel']!=s['overlap_owner_panel'])
        edits.append(dict(id=s['id'],kind='join',overlap_owner_panel=other,width_mm=15))
    b=generate_net(c,dict(seam_overrides=edits))
    assert b['status']=='passed' and a['cover_checks']==b['cover_checks'] and a['areas']==b['areas']
    assert a['foldback']==b['foldback']

def test_opening_on_receiver_conflict_is_located_without_narrowing():
    c=cover();p=next(p for p in c['panels'] if p['side']=='y-')
    p['holes']=[dict(points=[[5,30],[5,50],[10,50],[10,30]],closed=True,orientation='cw')]
    n=generate_net(c)
    assert n['status']=='failed'
    issue=next(d for d in n['diagnostics'] if d['code']=='tab_outside_receiving_material')
    assert issue['location'] and issue['refs'] and issue['candidates']
    assert all(t['width_mm']==15 for t in n['overlaps'])

def test_corner_collision_has_two_seam_refs_and_location():
    c=cover();settings=cut_settings(c);_,seams=adjacency(c['panels']);edits=[]
    # Adjacent top edges carry tabs from side panels into the same top corner.
    for s in seams:
        a,b=s['edge_a'].split('/')[0],s['edge_b'].split('/')[0]
        if 'z+' in (a,b) and ('x+' in (a,b) or 'y+' in (a,b)):
            edits.append(dict(id=s['id'],kind='join',overlap_owner_panel=a if a!='z+' else b,width_mm=15))
    settings['seam_overrides']=edits;n=generate_net(c,settings)
    issue=next(d for d in n['diagnostics'] if d['code']=='folded_corner_collision')
    assert n['status']=='failed' and len(issue['refs'])==2 and len(issue['location'])==2 and issue['candidates']
    assert [t['width_mm'] for t in n['overlaps']]==[15,15]
    assert issue['coordinate_space']=='receiving_uv_mm' and issue['geometry']['type']=='Polygon'
    for candidate in issue['candidates']:
        assert candidate['preview']['width_mm']==15
        alternative=copy.deepcopy(settings)
        for edit in alternative['seam_overrides']:
            if edit['id']==candidate['seam_id']:edit['overlap_owner_panel']=candidate['panel_key']
        assert generate_net(c,alternative)['status']=='passed'

def test_excess_width_cannot_silently_clip():
    c=cover();s=next(s for s in net()['seams'] if s['kind']=='join');s=dict(s,width_mm=150)
    n=generate_net(c,dict(seam_overrides=[{k:s[k] for k in ['id','kind','overlap_owner_panel','width_mm']}]))
    assert n['status']=='failed' and any(t['width_mm']==150 for t in n['overlaps'])
