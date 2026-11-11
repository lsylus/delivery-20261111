import math
import cadquery as cq
import pytest
from helpers import ROOT
from thermal_drawings.blanket.developable import Developable
@pytest.mark.parametrize('kind',['CYLINDER','CONE'])
def test_exact_length_and_foldback(kind):
 shape=cq.Solid.makeCylinder(30,70) if kind=='CYLINDER' else cq.Solid.makeCone(30,10,70)
 face=next(f for f in shape.Faces() if f.geomType()==kind);m=Developable(face);r=m.report()
 assert r['mapping_type']=='isometric'
 assert max(p['maximum_foldback_error_mm'] for p in r['pieces'])<1e-6
 lengths=r['pieces'][0]['lengths']
 assert sorted([lengths['bottom_arc_mm'],lengths['top_arc_mm']])==pytest.approx(sorted([60*math.pi,60*math.pi if kind=='CYLINDER' else 20*math.pi]))
 assert lengths['generator_mm']==pytest.approx(70 if kind=='CYLINDER' else math.hypot(70,20))
@pytest.mark.parametrize('file,kind',[('fuel-tank','CYLINDER'),('conical-support','CONE')])
def test_real_native_surface(file,kind):
 shape=cq.Shape.importBrep(str(ROOT/f'fixtures/real-derived/b13/{file}.brep'))
 face=max((f for f in shape.Faces() if f.geomType()==kind),key=lambda f:f.Area())
 m=Developable(face);u0,u1,_,_=m.bounds;r=m.report([(u0+u1)/2])
 assert len(r['pieces'])==2 and max(p['maximum_foldback_error_mm'] for p in r['pieces'])<1e-6
 assert r['native_area_mm2']==pytest.approx(face.Area())
def test_cut_outside_chart_rejected():
 face=next(f for f in cq.Solid.makeCylinder(10,20).Faces() if f.geomType()=='CYLINDER')
 with pytest.raises(ValueError,match='invalid_user_surface_cuts'):Developable(face).report([1e99])

def test_exact_cone_drawing_has_arcs_not_polyline_approximation():
 from thermal_drawings.blanket.developable import drawing
 from helpers import model_for
 shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/conical-support.brep'))
 model=model_for(shape);_,face,ref=next(x for x in model.faces if x[1].geomType()=='CONE')
 report=Developable(face).report();document=drawing(report,ref,'r')
 assert report['rectangular_trim']
 assert sum(e['kind']=='arc' for e in document['entities'])==2
 assert all(e['kind']!='polyline' for e in document['entities'])
