"""Installation-frame geometry; source occurrences are never transformed in place."""
import io
import hashlib
import math
import cadquery as cq
from geometry_core.transforms import rigid_transform_from_values, location_from_rigid_transform

EPS = 1e-6  # geometric reconstruction tolerance, not a manufacturing allowance


class BlanketError(ValueError):
    pass


def shape_hash(shape):
    stream = io.BytesIO()
    shape.exportBrep(stream)
    return hashlib.sha256(stream.getvalue()).hexdigest()


class Frame:
    def __init__(self, value):
        self.value = value
        axes = [value[k] for k in ('x_axis','y_axis','z_axis')]
        if not all(math.isfinite(v) for row in [value['origin'], *axes] for v in row):
            raise BlanketError('invalid_installation_frame')
        rotation = [[axes[j][i] for j in range(3)] for i in range(3)]
        try:
            transform = rigid_transform_from_values(rotation, value['origin'])
        except ValueError as error:
            raise BlanketError('invalid_installation_frame: ' + str(error)) from error
        self.location = cq.Location(location_from_rigid_transform(transform))

    def local(self, shape):
        return shape.moved(self.location.inverse)

    def world(self, shape):
        return shape.moved(self.location)

    def point(self, xyz):
        o=self.value['origin']; axes=[self.value[k] for k in ('x_axis','y_axis','z_axis')]
        return [o[i]+sum(xyz[j]*axes[j][i] for j in range(3)) for i in range(3)]


def bounds(shape):
    b=shape.BoundingBox()
    return [b.xmin,b.ymin,b.zmin], [b.xmax,b.ymax,b.zmax]


def select(parameters, model):
    if parameters['model_ref'] != model.model_ref:
        raise BlanketError('needs_reselection: model revision mismatch')
    ids=parameters['target_instances']
    if len(ids)!=len(set(ids)):
        raise BlanketError('duplicate target instance')
    chosen=[o for o in model.occurrences if o.id in ids]
    if len(chosen)!=len(ids):
        raise BlanketError('needs_reselection: unknown occurrence')
    frame=Frame(parameters['installation_frame'])
    local=[frame.local(o.shape.copy()) for o in chosen]
    # A regular equipment envelope may contain cavities, but its external shell
    # must be a single aligned rectangular box. Arbitrary unions belong to B13.
    if len(local)!=1 or len(local[0].Solids())!=1 or not local[0].isValid():
        raise BlanketError('unsupported_B13: select one regular box occurrence')
    solid=local[0].Solids()[0]
    outer=solid.outerShell()
    if len(outer.Faces())!=6 or any(f.geomType()!='PLANE' or len(f.Edges())!=4 or f.innerWires() for f in outer.Faces()):
        raise BlanketError('unsupported_B13: exterior is not a rectangular box')
    low,high=bounds(outer)
    dims=[b-a for a,b in zip(low,high)]
    if min(dims)<=EPS or abs(low[2])>EPS:
        raise BlanketError('installation plane must coincide with equipment bottom')
    sides={}
    for face in outer.Faces():
        lo,hi=bounds(face)
        flat=[i for i in range(3) if hi[i]-lo[i]<EPS]
        if len(flat)!=1:
            raise BlanketError('unsupported_B13: box axes differ from installation frame')
        axis=flat[0]; side=('x','y','z')[axis]+('-' if abs(lo[axis]-low[axis])<EPS else '+')
        if side in sides:
            raise BlanketError('unsupported_B13: duplicate exterior side')
        sides[side]=face
    if set(sides)!={'x-','x+','y-','y+','z-','z+'}:
        raise BlanketError('unsupported_B13: incomplete exterior box')
    source_refs={}
    for ref in chosen[0].refs:
        _, face, _=model.resolve(ref)
        f=frame.local(face.copy())
        for side,outer_face in sides.items():
            if (f.Center()-outer_face.Center()).Length<EPS and abs(f.Area()-outer_face.Area())<EPS:
                source_refs[side]=ref
    installation=parameters.get('installation_face')
    if installation is not None and installation!=source_refs.get('z-'):
        raise BlanketError('needs_reselection: installation face differs from bottom plane')
    for field in ('included_faces','excluded_faces'):
        if any(r not in source_refs.values() for r in parameters[field]):
            raise BlanketError('needs_reselection: only exterior box faces are supported')
        if len(parameters[field])!=len({str(r) for r in parameters[field]}):
            raise BlanketError('duplicate face selection')
    if any(r in parameters['excluded_faces'] for r in parameters['included_faces']):
        raise BlanketError('conflicting face selection')
    return dict(frame=frame,shape=solid,low=low,high=high,dimensions=dims,source_refs=source_refs,
                source_hashes={o.id:shape_hash(o.shape) for o in chosen})
