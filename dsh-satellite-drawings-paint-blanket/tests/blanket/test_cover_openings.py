import copy
import pytest
import cadquery as cq
from thermal_drawings.blanket.pipeline import generate
from helpers import fixture,check,opening


@pytest.mark.parametrize('side',['x-','x+','y-','y+','z+'])
def test_opening_removed_from_manufacturing_but_capped_for_evaluation(side,tmp_path):
    p,m=fixture();p['openings']=[opening(side)]
    r=generate(p,m,'opening',tmp_path)
    native=cq.Shape.importBrep(str(tmp_path/'manufacturing.brep'))
    evaluation=cq.Shape.importBrep(str(tmp_path/'evaluation.brep'))
    assert native.Area()==pytest.approx(5*105*105-100)
    assert sum(len(f.innerWires()) for f in native.Faces())==1
    assert evaluation.Volume()==pytest.approx(105**3)
    assert len(r['panels'])==5 and len(r['closures'])==2
    assert all(c['evaluation_only'] for c in r['closures'])
    assert check(r,'volume_ratio')['observed']['ratio']==pytest.approx(1.157625)
    assert r['status']=='passed'


@pytest.mark.parametrize('points',[[[0,0],[10,0],[10,10],[0,10]],[[20,20],[30,30],[20,30],[30,20]],[[200,20],[210,20],[210,30],[200,30]],[[20,20],[25,20],[30,20]]])
def test_invalid_openings_fail_closed(points):
    p,m=fixture();o=opening();o['loop']['points']=points;p['openings']=[o]
    with pytest.raises(ValueError):generate(p,m,'invalid')


def test_duplicate_and_overlapping_openings_rejected():
    p,m=fixture();p['openings']=[opening(),opening(id_='second')]
    with pytest.raises(ValueError,match='invalid_opening'):generate(p,m,'overlap')


def test_explicit_face_exclusion_becomes_evaluation_only_closure(tmp_path):
    p,m=fixture();top=next(r for r in m.occurrences[0].refs if r['signature']['normal'][2]>.9)
    p['excluded_faces']=[top]
    r=generate(p,m,'excluded',tmp_path)
    assert len(r['panels'])==4 and r['status']=='passed'
    assert {c['id'] for c in r['closures']}=={'excluded:z+','installation-bottom'}
    assert cq.Shape.importBrep(str(tmp_path/'manufacturing.brep')).Area()==pytest.approx(4*105**2)
