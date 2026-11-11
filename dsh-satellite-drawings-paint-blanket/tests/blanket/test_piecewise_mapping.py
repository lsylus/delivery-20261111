import cadquery as cq
import pytest
from helpers import ROOT
from thermal_drawings.blanket.segmentation import piecewise
def test_sphere_has_nonzero_surface_strain_and_deviation():
 face=next(f for f in cq.Solid.makeSphere(30).Faces() if f.geomType()=='SPHERE')
 r=piecewise(face,1.,.4)
 assert r['mapping_type']=='piecewise' and r['status']=='blocked' and r['manufacturing_tolerance'] is None
 assert r['maximum_chord_edge_error_mm']<1e-6
 assert r['maximum_surface_chord_strain']>0 and r['maximum_sampled_deviation_mm']>0
def test_real_doubly_curved_face_numeric_error():
 shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/fuel-tank.brep'))
 face=max((f for f in shape.Faces() if f.geomType()=='SPHERE'),key=lambda f:f.Area())
 coarse=piecewise(face,2.,.4);fine=piecewise(face,.5,.2)
 assert fine['triangle_count']>coarse['triangle_count']>0
 assert fine['maximum_sampled_deviation_mm']<coarse['maximum_sampled_deviation_mm']
 assert fine['maximum_surface_chord_strain']<coarse['maximum_surface_chord_strain']
@pytest.mark.parametrize('value',[0,-1,float('inf'),float('nan'),101])
def test_parameter_extremes_rejected(value):
 with pytest.raises(ValueError):piecewise(cq.Solid.makeSphere(10).Faces()[0],value)
