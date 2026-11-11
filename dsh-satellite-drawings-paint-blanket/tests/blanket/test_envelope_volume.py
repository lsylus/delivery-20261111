import pytest
import cadquery as cq
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.volume import closed_volume,close
from helpers import fixture,check


@pytest.mark.parametrize('dims,expected', [([100,100,100],'pass'),([100,100,120],'pass'),([100,100,120.000001],'fail'),([100,100,99.999999],'fail'),([110,110,100],'fail')])
def test_independent_volume_inclusive_boundaries(dims,expected):
    p,m=fixture();p['dimensions_mm']=dims;r=generate(p,m,'ratio')
    assert check(r,'volume_ratio')['status']==expected


def test_volume_pass_does_not_mask_local_penetration_or_coverage():
    p,m=fixture();p['dimensions_mm']=[95,110,110]
    r=generate(p,m,'penetrating')
    assert check(r,'volume_ratio')['status']=='pass'
    assert check(r,'coverage')['status']=='fail' and check(r,'penetration')['status']=='fail'
    assert r['status']=='failed'


def test_hollow_material_is_not_the_envelope_denominator():
    shell=cq.Solid.makeBox(100,100,100,cq.Vector(-50,-50,0)).cut(cq.Solid.makeBox(90,90,90,cq.Vector(-45,-45,5)))
    p,m=fixture(shape=shell);r=generate(p,m,'hollow')
    assert shell.Volume()==pytest.approx(271000)
    assert r['baseline']['volume_mm3']==pytest.approx(1000000)
    assert check(r,'volume_ratio')['observed']['ratio']==pytest.approx(1.157625)


def test_open_or_invalid_evaluation_cannot_supply_volume():
    box=cq.Solid.makeBox(100,100,100);faces=box.Faces()
    with pytest.raises(ValueError):closed_volume(cq.Compound.makeCompound(faces[:-1]))
    with pytest.raises(ValueError):close(faces[:-1],[])
    with pytest.raises(ValueError):closed_volume(cq.Compound.makeCompound([box,box.translate((200,0,0))]))


def test_thin_exterior_escape_cannot_be_hidden_by_native_boolean_tolerance():
    p,m=fixture((.000002,.1,.1));p['dimensions_mm']=[.0000011,.145,.145]
    r=generate(p,m,'thin-escape')
    assert check(r,'volume_ratio')['status']=='pass'
    assert check(r,'coverage')['status']=='fail' and r['status']=='failed'
    assert check(r,'coverage')['observed']['exterior_escape_mm'][0]>4e-7
