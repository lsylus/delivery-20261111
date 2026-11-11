"""Deterministic planar paint candidates derived from exact current FaceRefs."""
from collections import deque
import hashlib
import math


NORMAL_TOLERANCE = 1e-8
PLANE_TOLERANCE_MM = 1e-5
OPPOSITE_AREA_TOLERANCE = 0.05
MAX_PLATE_THICKNESS_RATIO = 0.30


def _dot(left, right):
    return sum(a*b for a, b in zip(left, right))


def _sub(left, right):
    return [a-b for a, b in zip(left, right)]


def _coplanar(left, right):
    a, b = left['signature'], right['signature']
    if _dot(a['normal'], b['normal']) < 1-NORMAL_TOLERANCE:
        return False
    return abs(_dot(_sub(b['centroid_mm'], a['centroid_mm']), a['normal'])) <= PLANE_TOLERANCE_MM


def _groups(items):
    by_id = {ref['entity_id']: ref for ref in items}
    pending = set(by_id)
    result = []
    while pending:
        seed_id = min(pending)
        seed = by_id[seed_id]
        compatible = {entity_id for entity_id in pending if _coplanar(seed, by_id[entity_id])}
        connected = set()
        queue = deque([seed_id])
        while queue:
            entity_id = queue.popleft()
            if entity_id in connected or entity_id not in compatible:
                continue
            connected.add(entity_id)
            queue.extend(by_id[entity_id]['signature']['adjacency'])
        # Some exporters split one planar patch without preserving a shared-edge
        # relation. Keep those patches separate rather than inventing continuity.
        pending -= connected
        result.append([by_id[entity_id] for entity_id in sorted(connected)])
    return result


def _direction(normal):
    index = max(range(3), key=lambda i: abs(normal[i]))
    if abs(normal[index]) < .95:
        return 'VECTOR'
    return ('+' if normal[index] >= 0 else '-') + 'XYZ'[index]


def _group_id(instance_id, refs):
    value = instance_id + '\0' + '\0'.join(ref['entity_id'] for ref in refs)
    return 'paint-face-group-' + hashlib.sha256(value.encode()).hexdigest()[:20]


def _candidate(instance_id, instance_name, refs, maximum_area, projected_area, plate_ratio, supported):
    area = sum(ref['signature']['area_mm2'] for ref in refs)
    area_ratio = area/maximum_area if maximum_area else 0
    coverage = min(1., area/projected_area) if projected_area else 0
    plate_score = max(0., 1-plate_ratio/MAX_PLATE_THICKNESS_RATIO)
    score = .50*area_ratio + .30*coverage + .20*plate_score
    default = supported and plate_ratio <= MAX_PLATE_THICKNESS_RATIO and area_ratio >= .5 and score >= .65
    normal = refs[0]['signature']['normal']
    weighted = [sum(ref['signature']['centroid_mm'][i]*ref['signature']['area_mm2'] for ref in refs)/area for i in range(3)]
    reasons = ['planar_connected_group', f'component_area_ratio={area_ratio:.6f}',
               f'projected_coverage={coverage:.6f}', f'plate_thickness_ratio={plate_ratio:.6f}']
    return dict(group_id=_group_id(instance_id, refs), instance_id=instance_id, instance_name=instance_name,
                target_face_refs=refs, area_mm2=area, centroid_mm=weighted, normal=normal,
                direction_label=_direction(normal), side_label='unassigned', default_paint_type='unassigned',
                confidence=dict(score=score, level='high' if default else 'medium' if score >= .4 else 'low', reasons=reasons),
                recommended=default, selectable=supported, topology_status='valid' if supported else 'unsupported_shell',
                opposite_group_id=None, diagnostic=None if supported else dict(code='solid_required', message='Shell-only components are not safe paint targets'),
                _component_area_ratio=area_ratio)


def _pair_opposites(groups):
    for index, left in enumerate(groups):
        candidates = []
        for right in groups[index+1:]:
            if _dot(left['normal'], right['normal']) > -1+NORMAL_TOLERANCE:
                continue
            if abs(left['area_mm2']-right['area_mm2'])/max(left['area_mm2'], right['area_mm2']) > OPPOSITE_AREA_TOLERANCE:
                continue
            delta = _sub(right['centroid_mm'], left['centroid_mm'])
            axial = abs(_dot(delta, left['normal']))
            lateral = math.sqrt(max(0., _dot(delta, delta)-axial*axial))
            if lateral > max(PLANE_TOLERANCE_MM, axial*.05):
                continue
            candidates.append((lateral, abs(left['area_mm2']-right['area_mm2']), right))
        if candidates:
            right = min(candidates, key=lambda item: item[:2])[2]
            if right['opposite_group_id'] is None:
                left['opposite_group_id'] = right['group_id']
                right['opposite_group_id'] = left['group_id']


def _reference_name(value):
    normalized = value.casefold()
    return any(token in normalized for token in ('envelope', 'reference', '包络'))


def recommend(model, revision_id, instance_names=None):
    """Return planar candidates without weakening exact FaceRef identity.

    ``Model`` has already enforced native BRep validity and signature equality.
    Unsupported shell-only occurrences remain visible but are never selected.
    """
    names = instance_names or {}
    groups, diagnostics = [], []
    for occurrence in model.occurrences:
        planar = [ref for owner, face, ref in model.faces
                  if owner is occurrence and face.geomType() == 'PLANE' and ref['signature']['area_mm2'] > 0]
        bounds = occurrence.shape.BoundingBox()
        extents = sorted((bounds.xlen, bounds.ylen, bounds.zlen), reverse=True)
        projected_area = extents[0]*extents[1]
        plate_ratio = extents[2]/extents[1] if extents[1] > 0 else math.inf
        supported = bool(occurrence.shape.Solids())
        grouped = _groups(planar)
        maximum_area = max((sum(ref['signature']['area_mm2'] for ref in group) for group in grouped), default=0)
        name = names.get(occurrence.id, occurrence.id)
        candidates = [_candidate(occurrence.id, name, group, maximum_area, projected_area, plate_ratio, supported)
                      for group in grouped]
        _pair_opposites(candidates)
        candidates.sort(key=lambda item: (-item['recommended'], -item['confidence']['score'], -item['area_mm2'], item['group_id']))
        groups.extend(candidates)
        if not supported:
            diagnostics.append(dict(code='solid_required', instance_id=occurrence.id, instance_name=name,
                                    message='Shell-only component candidates are not selectable'))
    for invalid in getattr(model, 'invalid_occurrences', []):
        planar = [ref for ref in invalid['refs'] if ref['signature']['type'] == 'PLANE'
                  and ref['signature']['normal'] is not None and ref['signature']['area_mm2'] > 0]
        grouped = _groups(planar)
        maximum_area = max((sum(ref['signature']['area_mm2'] for ref in group) for group in grouped), default=0)
        name = names.get(invalid['id'], invalid['id'])
        for refs in grouped:
            candidate = _candidate(invalid['id'], name, refs, maximum_area, maximum_area, math.inf, False)
            candidate.update(topology_status='invalid', diagnostic=dict(code=invalid['code'], message='Invalid topology requires repair before paint generation'))
            groups.append(candidate)
        diagnostics.append(dict(code=invalid['code'], instance_id=invalid['id'], instance_name=name,
                                message='Invalid topology candidates are visible but not selectable'))
    if groups:
        active = [group for group in groups if group['selectable'] and not _reference_name(group['instance_name'])]
        active = active or [group for group in groups if group['selectable']] or groups
        total_area = sum(group['area_mm2'] for group in active)
        center = [sum(group['centroid_mm'][i]*group['area_mm2'] for group in active)/total_area for i in range(3)]
        maximum = max(group['area_mm2'] for group in active)
        assembly_major = {
            group['group_id'] for group in active
            if (group['area_mm2'] >= maximum*.5
                and group['_component_area_ratio'] >= .5
                and group['confidence']['score'] >= .4)
        }
        for group in groups:
            radial = _sub(group['centroid_mm'], center)
            direction = _dot(group['normal'], radial)
            group['side_label'] = 'exterior' if direction > PLANE_TOLERANCE_MM else 'interior' if direction < -PLANE_TOLERANCE_MM else 'undetermined'
            group['default_paint_type'] = 'white' if group['side_label'] == 'exterior' else 'black' if group['side_label'] == 'interior' else 'unassigned'
            if group['area_mm2'] < maximum*.04:
                group['recommended'] = False
                group['confidence']['reasons'].append('below_assembly_major_surface_threshold')
            reference = _reference_name(group['instance_name'])
            if reference:
                group['recommended'] = False
                group['confidence']['score'] = max(0, group['confidence']['score']-.35)
                group['confidence']['reasons'].append('reference_envelope_name_hint')
            elif assembly_major and group['group_id'] not in assembly_major:
                group['recommended'] = False
                group['confidence']['reasons'].append('not_assembly_major_body_surface')
            elif group['group_id'] in assembly_major:
                group['recommended'] = True
                group['confidence']['level'] = 'high'
                group['confidence']['reasons'].append('assembly_major_body_surface')
        by_id = {group['group_id']: group for group in groups}
        for group in groups:
            opposite = by_id.get(group['opposite_group_id'])
            if opposite is None or group['group_id'] > opposite['group_id'] or group['side_label'] != opposite['side_label']:
                continue
            group['side_label'], opposite['side_label'] = 'side-a', 'side-b'
            group['default_paint_type'] = opposite['default_paint_type'] = 'unassigned'
        for group in groups:
            group.pop('_component_area_ratio')
    return dict(schema_version=1, revision_id=revision_id, model_ref=model.model_ref,
                status='needs_review' if diagnostics else 'passed', groups=groups, diagnostics=diagnostics)
