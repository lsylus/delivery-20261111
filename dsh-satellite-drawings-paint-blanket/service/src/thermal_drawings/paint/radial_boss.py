"""Native attachment footprint for bounded radial bosses on a cylinder.

No engineering classification is inferred: the caller must supply an explicit
boss boundary rule. The topological component is isolated by the exact mouth,
and all its faces must lie outside the target's cylindrical interior. This
admits the real motor's inclined, stepped posts without a parallel-cap fiction.
"""
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopAbs import TopAbs_REVERSED
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from .curved_native import common, support
from .selection import PaintError


def attached_component(target, wire, occurrence, model, budget):
    if target.geomType() != 'CYLINDER' or target.wrapped.Orientation() == TopAbs_REVERSED:
        return None
    rows = [(f, ref) for owner, f, ref in model.faces if owner is occurrence]
    root = next((i for i, (f, _) in enumerate(rows) if f.isSame(target)), None)
    if root is None:
        raise PaintError('radial_boss_identity', 'Target topology changed', 'failed')
    edges = [f.Edges() for f, _ in rows]
    mouth = wire.Edges()
    connected = lambda a, b: any(x.isSame(y) for x in a for y in b)
    start = [i for i in range(len(rows)) if i != root and connected(edges[i], mouth)]
    component, pending = set(), list(start)
    while pending:
        i = pending.pop()
        if i in component:
            continue
        component.add(i)
        if len(component) > 16:
            return None
        for j in range(len(rows)):
            if j == root or j in component:
                continue
            budget.consume(pairs=1)
            if connected(edges[i], edges[j]): pending.append(j)
    if not component:
        return None
    shared = [e for i in component for e in edges[i] if connected([e], edges[root])]
    if not all(connected([e], mouth) for e in shared) or not all(connected([e], shared) for e in mouth):
        return None  # A component attached at another mouth/outer edge is ambiguous.
    if any(rows[i][0].geomType() not in ('PLANE', 'CYLINDER', 'CONE') for i in component):
        return None
    cylinder = BRepAdaptor_Surface(target.wrapped).Cylinder()
    origin = cq.Vector(cylinder.Location().Coord())
    axis = cq.Vector(cylinder.Axis().Direction().Coord())
    # Curved faces can extend axially beyond all their topological vertices.
    # Bound the entire native component before testing cylindrical intrusion.
    local = cq.Plane(origin=origin.toTuple(), normal=axis.toTuple()).toLocalCoords(
        cq.Compound.makeCompound([rows[i][0] for i in component]))
    box = Bnd_Box();BRepBndLib.AddOptimal_s(local.wrapped, box, False, True)
    if box.IsVoid() or box.IsOpen():return None
    bounds = box.Get();lo, hi = bounds[2]-10, bounds[5]+10
    inside = cq.Solid.makeCylinder(cylinder.Radius()-1e-5, hi-lo, origin+axis*lo, axis)
    proofs = []
    for i in sorted(component):
        face, ref = rows[i]
        budget.consume(pairs=1)
        intrusion = sum(f.Area() for f in common(face, inside).Faces())
        if intrusion > 1e-7:
            return None
        proofs.append(dict(source_ref=ref, surface_type=face.geomType(), native_area_mm2=face.Area(), inside_cylinder_area_mm2=intrusion))
    footprint = support(target, wire)
    if not footprint.isValid() or footprint.Area() <= 1e-7:
        raise PaintError('radial_boss_footprint', 'Invalid native attachment footprint', 'failed')
    return [(rows[i][0], rows[i][1]) for i in sorted(component)], footprint, dict(
        method='exact_native_mouth_and_outward_attached_component', native_mouth_area_mm2=footprint.Area(),
        component_faces=proofs, target_radius_mm=cylinder.Radius(), numerical_interior_guard_mm=1e-5,
        engineering_classification='explicit_boundary_rule_only', manufacturing_approved=False,
        protection_scope='Every actual exposed face in the isolated boss component, including stepped caps and sidewalls; no projection onto a fictional parallel cap')
