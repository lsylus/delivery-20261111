import copy
import math
import pytest
import cadquery as cq
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.selection import Frame,shape_hash
from helpers import fixture,check


def test_100_box_linear_allowance_bottom_anchor_and_real_native(tmp_path):
    p,m=fixture();before=shape_hash(m.occurrences[0].shape)
    r=generate(p,m,'r1',tmp_path)
    assert r['dimensions_mm']==[105,105,105] and r['status']=='passed'
    assert check(r,'volume_ratio')['observed']['ratio']==pytest.approx(1.157625,abs=1e-12)
    native=cq.Shape.importBrep(str(tmp_path/'manufacturing.brep'))
    b=native.BoundingBox()
    assert [b.xmin,b.xmax,b.ymin,b.ymax,b.zmin,b.zmax]==pytest.approx([-52.5,52.5,-52.5,52.5,0,105],abs=1e-6)
    assert len(native.Faces())==5 and not native.Solids()
    assert not any(abs(f.Center().z)<1e-7 and abs(f.normalAt().z)>.99 for f in native.Faces())
    assert shape_hash(m.occurrences[0].shape)==before
    assert (tmp_path/'cover.glb').read_bytes()[:4]==b'glTF'


@pytest.mark.parametrize('angles',[(17,31,53),(90,0,0),(0,180,0),(123,47,-81)])
def test_rigid_installation_frame_preserves_relative_geometry(angles,tmp_path):
    location=cq.Location(cq.Vector(243,-17,92),angles)
    transform=location.wrapped.Transformation()
    frame=dict(origin=[243,-17,92],units='mm',handedness='right',**{key:[transform.Value(i,j) for i in (1,2,3)] for j,key in enumerate(('x_axis','y_axis','z_axis'),1)})
    p,m=fixture(frame=frame);before=shape_hash(m.occurrences[0].shape)
    r=generate(p,m,'rotation',tmp_path)
    local=Frame(frame).local(cq.Shape.importBrep(str(tmp_path/'evaluation.brep')))
    b=local.BoundingBox()
    assert [b.xlen,b.ylen,b.zlen,b.zmin]==pytest.approx([105,105,105,0],abs=1e-6)
    assert check(r,'volume_ratio')['observed']['ratio']==pytest.approx(1.157625,abs=1e-12)
    assert r['status']=='passed' and shape_hash(m.occurrences[0].shape)==before


@pytest.mark.parametrize('dims',[(1000,2,.1),(.02,10,500),(12,27,89)])
def test_thin_long_box_independent_xyz(dims):
    p,m=fixture(dims);p['allowance']['factors']=[1.01,1.03,1.07]
    r=generate(p,m,'r');assert r['dimensions_mm']==pytest.approx([d*f for d,f in zip(dims,[1.01,1.03,1.07])])
    assert check(r,'volume_ratio')['observed']['ratio']==pytest.approx(1.01*1.03*1.07,abs=1e-10)
    assert r['status']=='passed'


@pytest.mark.parametrize('axes',[[[2,0,0],[0,1,0],[0,0,1]],[[1,0,0],[0,1,0],[0,0,-1]],[[1,0,0],[1,1,0],[0,0,1]]])
def test_nonrigid_frame_rejected(axes):
    p,m=fixture()
    for key,value in zip(('x_axis','y_axis','z_axis'),axes):p['installation_frame'][key]=value
    with pytest.raises(ValueError):generate(p,m,'bad')


def test_unsupported_nonbox_and_wrong_bottom_are_not_silently_enveloped():
    p,m=fixture(shape=cq.Solid.makeCylinder(10,100))
    with pytest.raises(ValueError,match='unsupported_B13'):generate(p,m,'cylinder')
    p,m=fixture();p['installation_frame']['origin'][2]=1
    with pytest.raises(ValueError,match='installation plane'):generate(p,m,'wrong')
