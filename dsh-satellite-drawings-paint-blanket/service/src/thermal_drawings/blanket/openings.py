"""Explicit planar polygon openings; evaluation caps are separate native faces."""
import cadquery as cq
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from .selection import BlanketError, EPS


def face(points, placement):
    vertices=[cq.Vector(*placement(p)) for p in points]
    return cq.Face.makeFromWires(cq.Wire.makePolygon(vertices,close=True))


def cut_openings(width,height,openings,placement):
    domain=Polygon([(0,0),(width,0),(width,height),(0,height)])
    polys=[];caps=[];holes=[]
    for opening in openings:
        points=opening['loop']['points'];poly=Polygon(points)
        if (not poly.is_valid or poly.area<=EPS*EPS or not domain.contains(poly)
                or domain.boundary.distance(poly)<=EPS or any(poly.intersects(p) for p in polys)):
            raise BlanketError('invalid_opening: must be simple, disjoint, strictly inside one panel')
        poly=orient(poly,sign=-1)
        points=[list(p) for p in list(poly.exterior.coords)[:-1]]
        holes.append(dict(points=points,closed=True,orientation='cw'))
        caps.append((opening['id'],face(points,placement)))
        polys.append(poly)
    outer=face(list(domain.exterior.coords)[:-1],placement)
    inner=[cap.outerWire() for _,cap in caps]
    native=cq.Face.makeFromWires(outer.outerWire(),inner)
    if not native.isValid() or abs(native.Area()-(domain.area-sum(p.area for p in polys)))>max(1e-6,domain.area*1e-9):
        raise BlanketError('invalid_opening_topology')
    return native,caps,holes
