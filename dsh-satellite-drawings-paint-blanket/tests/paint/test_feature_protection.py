import math
import pytest
from b08_cases import assembly, params, box, from_shapes, override
from thermal_drawings.paint.pipeline import generate


def test_real_hole_boss_and_rib_material_rules():
    m=assembly(features=True);p=params(m);p['boss_additional_offset_mm']=3
    r=generate(p,m,'r')
    assert r['status']=='passed',r['diagnostics']
    holes=[x for x in r['regions'] if x['kind']=='hole']
    bosses=[x for x in r['regions'] if x['kind']=='boss']
    assert len(holes)==1 and len(bosses)==2
    assert holes[0]['area_mm2']==pytest.approx(math.pi*(7**2-4**2),rel=1e-6)
    assert len(holes[0]['loops'])==2
    assert sorted(x['area_mm2'] for x in bosses)==pytest.approx(sorted([math.pi*4**2,math.pi*(7**2-4**2)]),rel=1e-6)
    assert sorted(x['local_frame']['origin'][2] for x in bosses)==pytest.approx([0,6])
    rib=next(e for e in r['evidence'] if e.get('classification')=='rib')
    assert rib['projected_aspect_ratio']==pytest.approx(12.5,rel=1e-6)
    assert rib['override'] is None


def test_compact_rectangular_raised_feature_requires_classification_and_is_not_hole():
    plate=box(0,0,-5,100,80,5).fuse(box(20,20,0,10,8,6)).clean()
    m=from_shapes([plate])
    r=generate(params(m),m,'r')
    assert r['status']=='needs_review'
    assert any(d['code']=='feature_classification_unknown' for d in r['diagnostics'])
    assert not r['regions']


@pytest.mark.parametrize('kind,count,area',[('boss',2,100),('rib',1,None),('exclude',1,None),('unknown',1,None)])
def test_manual_classification_without_default_boss_expansion(kind,count,area):
    m=assembly();p=params(m)
    ref=next(r for o,f,r in m.faces if o is m.occurrences[1] and f.geomType()=='PLANE' and f.normalAt().z<-.9)
    p['overrides']=[override(ref,kind)]
    r=generate(p,m,'r')
    assert len(r['regions'])==count
    if area:
        boss=next(x for x in r['regions'] if x['kind']=='boss')
        assert boss['area_mm2']==pytest.approx(area,rel=1e-6) and boss['origin']=='manual'
    if kind=='unknown':assert r['status']=='needs_review'
