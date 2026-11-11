import copy
import json
import pytest
from thermal_drawings.blanket.pipeline import generate
from helpers import fixture,check,opening


def test_edits_and_json_restore_keep_original_baseline(tmp_path):
    p,m=fixture();first=generate(p,m,'first')
    p['dimensions_mm']=[100,110,100];p['openings']=[opening()]
    edited=generate(p,m,'second',previous=first['baseline'])
    assert edited['baseline']==first['baseline']
    path=tmp_path/'saved.json';path.write_text(json.dumps(edited))
    saved=json.loads(path.read_text());rebuilt=generate(saved['parameters'],m,'restored',previous=saved['baseline'])
    assert rebuilt['baseline']==first['baseline'] and rebuilt['checks']==edited['checks']
    assert rebuilt['panels'][0]['id']!=edited['panels'][0]['id']


def test_adjusting_oversized_cover_does_not_enlarge_denominator():
    p,m=fixture();r=generate(p,m,'r1');p['dimensions_mm']=[150,150,150]
    changed=generate(p,m,'r2',previous=r['baseline'])
    assert changed['baseline']==r['baseline'] and changed['status']=='failed'
    assert check(changed,'volume_ratio')['observed']['ratio']==pytest.approx(3.375)


@pytest.mark.parametrize('change',['model','instance','frame'])
def test_baseline_identity_changes_with_source_selection_or_frame(change):
    p,m=fixture();r=generate(p,m,'first')
    if change=='frame':
        p['installation_frame'].update(x_axis=[0,1,0],y_axis=[-1,0,0])
    else:
        from helpers import model_for
        m=model_for(m.occurrences[0].shape,instance='new' if change=='instance' else 'equipment',model_revision=2 if change=='model' else 1)
        p['model_ref']=m.model_ref;p['target_instances']=[m.occurrences[0].id]
    changed=generate(p,m,'second',previous=r['baseline'])
    assert changed['baseline']['id']!=r['baseline']['id'] and changed['baseline']['source_revision']=='second'


@pytest.mark.parametrize('field',['volume_mm3','dimensions_mm','algorithm'])
def test_tampered_saved_denominator_is_rejected(field):
    p,m=fixture();r=generate(p,m,'r1');base=copy.deepcopy(r['baseline'])
    if field=='volume_mm3':base[field]*=2
    elif field=='dimensions_mm':base['parameters'][field][0]*=2
    else:base[field]='other-algorithm'
    with pytest.raises(ValueError,match='baseline_integrity'):generate(p,m,'r2',previous=base)
