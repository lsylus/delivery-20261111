"""Deterministic B03 inputs; external STEP remains read-only and mandatory."""
from pathlib import Path
import cadquery as cq

SOURCE = Path('/data/qmh/satellite-plugins-20261029/microservice-refactor-shared-core')
CAD = SOURCE/'cad-assembly'
EXTERNAL = SOURCE.parent/'delivery-20261029/initial-data/thermal'
PARAMETERS = dict(intersection_distance_limit_mm=1e-5, zero_volume_tolerance_mm3=1e-5)

def box(origin=(0, 0, 0), size=(10, 10, 10)):
    return cq.Solid.makeBox(*size, pnt=cq.Vector(*origin))

def face(points, z=0):
    return cq.Face.makeFromWires(cq.Wire.makePolygon([cq.Vector(x,y,z) for x,y in points], close=True))

def rectangle(x=0, y=0, z=0, w=10, h=10):
    return face([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],z)

def patch_cases():
    left=rectangle()
    yield 'coincident',left,left,(100.,)
    yield 'overlap',left,rectangle(x=5),(50.,)
    yield 'separate',left,rectangle(x=11),()
    yield 'edge',left,rectangle(x=10),()
    yield 'point',left,rectangle(x=10,y=10),()
    for gap in (.099,.1,.101):
        yield f'gap-{gap}',left,rectangle(z=gap),()
    u=face([(0,0),(6,0),(6,6),(4,6),(4,2),(2,2),(2,6),(0,6)])
    yield 'multiple',u,rectangle(x=-1,y=3,w=8,h=2),(4.,4.)

def analytic_pairs():
    a=box()
    for name,origin,distance,volume,area in [
        ('separate',(11,0,0),1.,0.,None),
        ('touch',(10,0,0),0.,0.,100.),
        ('edge',(10,10,0),0.,0.,None),
        ('point',(10,10,10),0.,0.,None),
        ('overlap',(9,0,0),0.,100.,None),
        ('gap-0.099',(10.099,0,0),.099,0.,None),
        ('gap-0.1',(10.1,0,0),.1,0.,None),
        ('gap-0.101',(10.101,0,0),.101,0.,None),
    ]:
        yield name,a,box(origin),(distance,volume,area)
    yield 'containment',a,box((2.5,2.5,2.5),(5,5,5)),(0.,125.,None)
    bracket=box(size=(80,60,5)).fuse(box(size=(80,5,40))).clean()
    probe=box((10,20,20))
    yield 'L-source',bracket,probe,(15.,0.,None)
    yield 'L-envelope',box(size=(80,60,40)),probe,(0.,1000.,None)
    yield 'solid-sheet-contact',box(),rectangle(z=10),(0.,0.,100.)
    yield 'sheet-sheet',rectangle(),rectangle(),(0.,0.,100.)

def external_inputs():
    return {
        'contact':CAD/'backend/tests/satellite_fixtures/contact.step',
        'instances':CAD/'backend/tests/satellite_fixtures/instances.step',
        'solid-sheet':EXTERNAL/'solid-sheet/geometry.step',
        'real-gearbox':EXTERNAL/'real-gearbox/geometry.step',
    }
