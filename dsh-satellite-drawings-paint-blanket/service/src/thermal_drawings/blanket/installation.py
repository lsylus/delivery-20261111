"""Native, revision-bound installation coordinates for a selected occurrence."""
import math
import numpy as np
from geometry_core.solid_pairs import find_opposed_planar_contacts
from .selection import Frame, BlanketError, bounds, EPS
from .faceted_cover import native_bounds


def detect(model, target_instances, excluded_instances, maximum_gap_mm=.1):
    """Map neutral world-space contact facts back to revision-bound FaceRefs."""
    if (not isinstance(target_instances, list) or not target_instances
            or len(target_instances) != len(set(target_instances))):
        raise BlanketError('installation_target_required_or_duplicate')
    if (not isinstance(excluded_instances, list)
            or len(excluded_instances) != len(set(excluded_instances))):
        raise BlanketError('installation_exclusion_duplicate')
    occurrences = {occurrence.id: occurrence for occurrence in model.occurrences}
    if any(instance not in occurrences for instance in target_instances):
        raise BlanketError('installation_target_unknown')
    if any(instance not in occurrences for instance in excluded_instances):
        raise BlanketError('installation_excluded_unknown')
    excluded = set(excluded_instances)
    active_ids = [instance for instance in target_instances if instance not in excluded]
    if not active_ids:
        raise BlanketError('installation_target_required')
    target_scope = set(target_instances) | excluded
    supports = [(occurrence.id, occurrence.shape) for occurrence in model.occurrences
                if occurrence.id not in target_scope]
    contacts = []
    for instance in active_ids:
        target = occurrences[instance]
        contacts.extend(find_opposed_planar_contacts(
            target.id, target.shape, supports, maximum_gap_mm=maximum_gap_mm))

    grouped = {}
    for contact in contacts:
        grouped.setdefault((contact.target_key, contact.target_face_index), []).append(contact)
    candidates = []
    for key in sorted(grouped):
        rows = grouped[key]
        target = occurrences[key[0]]
        representative = max(rows, key=lambda row: row.contact_area_mm2)
        support_refs = [occurrences[row.support_key].refs[row.support_face_index] for row in rows]
        candidates.append(dict(
            target_face_ref=target.refs[key[1]],
            support_face_ref=occurrences[representative.support_key].refs[representative.support_face_index],
            support_face_refs=support_refs,
            gap_mm=representative.gap_mm,
            gap_range_mm=[min(row.gap_mm for row in rows), max(row.gap_mm for row in rows)],
            contact_area_mm2=sum(row.contact_area_mm2 for row in rows)))
    return dict(
        status='none' if not candidates else 'unique' if len(candidates) == 1 else 'ambiguous',
        maximum_gap_mm=float(maximum_gap_mm),
        candidates=candidates)


def measure(model, face_ref, setup):
    occurrence, face, _ = model.resolve(face_ref)
    if face.geomType() != 'PLANE':
        raise BlanketError('installation_requires_plane')
    if len(occurrence.shape.Solids()) != 1 or not occurrence.shape.isValid():
        raise BlanketError('installation_requires_complete_solid')
    direction=np.asarray(setup['x_direction'],dtype=float)
    if direction.shape!=(3,) or not np.isfinite(direction).all() or np.linalg.norm(direction)<1e-9:
        raise BlanketError('invalid_installation_x_direction')
    z=-np.array(face.normalAt().toTuple());z/=np.linalg.norm(z)
    x=direction/np.linalg.norm(direction);x-=np.dot(x,z)*z
    if np.linalg.norm(x)<1e-7:raise BlanketError('installation_x_parallel_to_normal')
    x/=np.linalg.norm(x);y=np.cross(z,x)
    angle=setup['rotation_deg'];offset=setup['offset_mm']
    if not math.isfinite(angle) or abs(angle)>180 or len(offset)!=2 or not all(math.isfinite(v) and abs(v)<=1e6 for v in offset):
        raise BlanketError('invalid_installation_origin_or_rotation')
    a=math.radians(angle);x=math.cos(a)*x+math.sin(a)*y;y=np.cross(z,x)
    # Remove arithmetic noise only, never rotate a measurable tilted axis.
    for vector in (x,y,z):vector[np.abs(vector)<1e-14]=0.;vector/=np.linalg.norm(vector)
    frame=dict(origin=list(face.Center().toTuple()),x_axis=x.tolist(),y_axis=y.tolist(),z_axis=z.tolist(),units='mm',handedness='right')
    local=Frame(frame).local(occurrence.shape.copy());low,high=bounds(local)
    if abs(low[2])>EPS:raise BlanketError('installation_face_not_supporting_bottom')
    if setup['origin_mode'] not in ('face_center','bounds_min'):raise BlanketError('invalid_installation_origin_mode')
    shift=np.array(offset)+(np.array(low[:2]) if setup['origin_mode']=='bounds_min' else 0)
    frame['origin']=(np.array(frame['origin'])+shift[0]*x+shift[1]*y).tolist()
    native=native_bounds(Frame(frame).local(occurrence.shape.copy()))
    return dict(kind='installation_frame',frame=frame,setup=setup,instance_id=occurrence.id,
                local_bounds_mm=[list(native[:3]),list(native[3:])],
                section_x_open_interval_mm=[native[0]+EPS,native[3]-EPS],
                source_face_count=len(occurrence.shape.Faces()),units='mm',
                origin_definition='Selected face plane; face center or projected occurrence XY bounding minimum, then local XY offset',
                bounds_definition='Native AddOptimal without triangulation, including shape tolerance; cuts must lie strictly inside the displayed interval',
                manufacturing_approved=False)


def validate_setup(parameters,model):
    if 'installation_setup' not in parameters:return
    if not parameters.get('installation_face'):raise BlanketError('installation_face_required_for_setup')
    report=measure(model,parameters['installation_face'],parameters['installation_setup'])
    if parameters['target_instances']!=[report['instance_id']]:raise BlanketError('installation_instance_mismatch')
    for key in ('origin','x_axis','y_axis','z_axis'):
        if not np.allclose(parameters['installation_frame'][key],report['frame'][key],rtol=0,atol=1e-8):
            raise BlanketError('installation_preview_mismatch: remeasure current coordinates')
