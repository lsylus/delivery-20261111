"""Current FaceRef resolution and bounded planar B-rep to UV conversion."""
from dataclasses import dataclass
import math
import time
import cadquery as cq
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

LENGTH_EPS = 1e-7
CHORD = 1e-7
AREA_EPS = 1e-9


class PaintError(RuntimeError):
    def __init__(self, code, message, status='needs_review', source_refs=None, observed=None):
        super().__init__(message)
        self.code, self.status = code, status
        self.source_refs = list(source_refs) if source_refs is not None else None
        self.observed = dict(observed or {})


@dataclass
class Budget:
    maximum_pairs: int = 10000
    maximum_points: int = 500000
    timeout_s: float = 60
    pairs: int = 0
    points: int = 0

    def __post_init__(self):
        if self.maximum_pairs < 0 or self.maximum_points < 0 or not math.isfinite(self.timeout_s) or self.timeout_s < 0:
            raise ValueError('Invalid paint budget')
        self.deadline = time.monotonic() + self.timeout_s

    def consume(self, pairs=0, points=0):
        if self.pairs+pairs > self.maximum_pairs or self.points+points > self.maximum_points or time.monotonic() > self.deadline:
            raise PaintError('budget_exhausted', f'Incomplete scan; no partial protection published; reserved_pairs={self.pairs}, requested_pairs={pairs}, maximum_pairs={self.maximum_pairs}')
        self.pairs += pairs
        self.points += points


@dataclass
class Occurrence:
    id: str
    shape: cq.Shape
    refs: list


class Model:
    def __init__(self, model_ref, occurrences, *, tolerant=False):
        self.model_ref, self.occurrences = model_ref, occurrences
        self.faces = []
        self.invalid_occurrences = []
        valid_occurrences = []
        for occ in occurrences:
            faces = occ.shape.Faces()
            if not occ.shape.isValid() or len(faces) != len(occ.refs):
                if tolerant:
                    self.invalid_occurrences.append(dict(id=occ.id, refs=occ.refs, code='invalid_brep'))
                    continue
                raise PaintError('invalid_brep', 'Invalid topology or face map', 'failed')
            start = len(self.faces)
            try:
                for face, ref in zip(faces, occ.refs, strict=True):
                    if any(ref[k] != v for k, v in model_ref.items()) or ref['instance_id'] != occ.id:
                        raise PaintError('needs_reselection', 'Foreign model/occurrence reference')
                    sig = ref['signature']
                    if (face.geomType() != sig['type'] or abs(face.Area()-sig['area_mm2']) > max(1e-6, face.Area()*1e-8)
                        or (face.Center()-cq.Vector(*sig['centroid_mm'])).Length > 1e-6):
                        raise PaintError('needs_reselection', 'BRep face ordering/signature changed')
                    self.faces.append((occ, face, ref))
            except PaintError as error:
                del self.faces[start:]
                if tolerant:
                    self.invalid_occurrences.append(dict(id=occ.id, refs=occ.refs, code=error.code))
                    continue
                raise
            valid_occurrences.append(occ)
        self.occurrences = valid_occurrences

    def resolve(self, ref):
        found = [(o, f, r) for o, f, r in self.faces if r == ref]
        if len(found) != 1:
            raise PaintError('needs_reselection', 'Missing or ambiguous exact FaceRef; no automatic rebinding')
        return found[0]


class Plane:
    def __init__(self, face):
        if face.geomType() != 'PLANE':
            raise PaintError('nonplanar_target', 'B08 requires a planar target; no silent flattening')
        self.origin = face.Center()
        self.z = face.normalAt().normalized()
        seed = cq.Vector(1, 0, 0) if abs(self.z.x) < .9 else cq.Vector(0, 1, 0)
        self.x = (seed - self.z * seed.dot(self.z)).normalized()
        self.y = self.z.cross(self.x).normalized()

    def uv(self, p):
        d = p-self.origin
        return (d.dot(self.x), d.dot(self.y))

    def gap(self, p):
        return (p-self.origin).dot(self.z)

    def frame(self, height=0):
        return dict(origin=list((self.origin+self.z*height).toTuple()), x_axis=list(self.x.toTuple()),
                    y_axis=list(self.y.toTuple()), z_axis=list(self.z.toTuple()), units='mm', handedness='right')


def ring(wire, plane, budget):
    points, _ = wire.sample(float(CHORD))
    budget.consume(points=len(points))
    polygon = Polygon([plane.uv(p) for p in points])
    if polygon.is_empty or not polygon.is_valid or polygon.area <= AREA_EPS:
        raise PaintError('invalid_loop', 'Invalid or degenerate sampled B-rep loop', 'failed')
    return polygon


def face_polygon(face, plane, budget):
    outer = ring(face.outerWire(), plane, budget)
    holes = [list(ring(w, plane, budget).exterior.coords) for w in face.innerWires()]
    poly = Polygon(outer.exterior.coords, holes)
    if not poly.is_valid:
        raise PaintError('invalid_domain', 'Invalid material domain', 'failed')
    return poly


def polygons(value):
    if value.is_empty:
        return []
    if value.geom_type == 'Polygon':
        return [value] if value.area > AREA_EPS else []
    return [p for g in getattr(value, 'geoms', []) for p in polygons(g)]


def loops(poly):
    poly = orient(poly, sign=1)
    return [dict(points=[list(p) for p in r.coords[:-1]], closed=True, orientation='ccw' if i == 0 else 'cw')
            for i, r in enumerate([poly.exterior, *poly.interiors])]
