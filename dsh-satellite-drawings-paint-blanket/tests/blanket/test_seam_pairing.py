import copy
import pytest
from thermal_drawings.blanket.seams import adjacency
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.panels import NetError
from net_helpers import cover,net,cut_settings

def test_eight_real_pairings_and_four_open_bottom_edges():
    c=cover();edges,seams=adjacency(c['panels'])
    assert len(edges)==20 and len(seams)==8
    assert len({e for s in seams for e in [s['edge_a'],s['edge_b']]})==16
    for s in seams:
        assert s['pair_orientation']=='opposite'
        assert edges[s['edge_a']]['world']==edges[s['edge_b']]['world'][::-1]

@pytest.mark.parametrize('kind',['cut','fold','join'])
def test_distinct_seam_semantics(kind):
    c=cover();settings=cut_settings(c);s=adjacency(c['panels'])[1][0]
    settings['seam_overrides']=[dict(id=s['id'],kind=kind,overlap_owner_panel='x+' if kind=='join' else None,width_mm=15 if kind=='join' else 0)]
    n=generate_net(c,settings)
    assert n['status']=='passed' and len(n['overlaps'])==(kind=='join')
    assert len(n['pieces'])==(4 if kind=='fold' else 5)

@pytest.mark.parametrize('bad',['unpaired','foreign_owner','double','fold_tab','cut_tab'])
def test_invalid_pairs_and_ownership_refused(bad):
    c=cover();s=adjacency(c['panels'])[1][0];edit=dict(id=s['id'],kind='join',overlap_owner_panel='x+',width_mm=15)
    if bad=='unpaired':edit['id']='installation-bottom-unpaired'
    if bad=='foreign_owner':edit['overlap_owner_panel']='z+'
    if bad=='fold_tab':edit['kind']='fold'
    if bad=='cut_tab':edit['kind']='cut'
    with pytest.raises(NetError):generate_net(c,dict(seam_overrides=[edit,edit] if bad=='double' else [edit]))

def test_nonmanifold_duplicate_face_rejected():
    c=cover();other=copy.deepcopy(c['panels'][0]);other['side']='copy';other['id']='copy';c['panels'].append(other)
    with pytest.raises(NetError,match='nonmanifold'):adjacency(c['panels'])
