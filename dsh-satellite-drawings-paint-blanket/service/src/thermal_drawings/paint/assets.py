"""Rehydrate B06 controlled immutable BRep assets, using the B02 face map."""
import json
import cadquery as cq
from geometry_core.transforms import rigid_transform_from_values, location_from_rigid_transform
from ..storage.assets import controlled, sha
from .selection import Model, Occurrence


REFERENCE_NAME_TOKENS = ('envelope', 'reference', '\u5305\u7edc')


def is_reference_instance(instance):
    name = instance.get('name', '').casefold()
    return any(token in name for token in REFERENCE_NAME_TOKENS)


def load_model(root, model, *, instance_ids=None, tolerant=False, exclude_reference_occurrences=False):
    snapshot = model['snapshot']
    assets = {}
    for a in model['artifacts']:
        path = controlled(root, a['relative_storage_path'])
        if path.stat().st_size != a['bytes'] or sha(path) != a['sha256']:
            raise ValueError('Model artifact integrity failed')
        assets[a['relative_storage_path'].split('/', 2)[2]] = path
    mapping = json.loads(assets[snapshot['mesh_map_asset']].read_text())
    if mapping['model_ref'] != snapshot['model_ref']:
        raise ValueError('Model map mismatch')
    selected = None if instance_ids is None else set(instance_ids)
    refs_by_instance = {}
    for entry in [*mapping['faces'], *mapping.get('unrenderable_faces', [])]:
        ref = entry['face_ref']
        if selected is not None and ref['instance_id'] not in selected:
            continue
        refs_by_instance.setdefault(ref['instance_id'], []).append(ref)
    for refs in refs_by_instance.values():
        # Render ranges and the non-display catalog are separate, but native
        # validation still needs every original face in its numeric order.
        # Preserve former ordering for legacy nonnumeric public entity IDs.
        if all(ref['entity_id'].startswith('face-') and ref['entity_id'][5:].isdigit() for ref in refs):
            refs.sort(key=lambda ref:int(ref['entity_id'][5:]))
    definition_assets = {d['id']: d['shape_asset'] for d in snapshot['definitions']}
    definitions = {}
    occurrences = []
    for instance in snapshot['instances']:
        refs = refs_by_instance.get(instance['instance_id'], [])
        if not refs:
            continue  # B02 map lists only physical leaves, never assembly aggregate duplicates.
        if exclude_reference_occurrences and is_reference_instance(instance):
            continue
        definition = instance['definition_id']
        if definition not in definitions:
            definitions[definition] = cq.Shape.importBrep(str(assets[definition_assets[definition]]))
        m = instance['world_transform']['matrix']
        transform = rigid_transform_from_values([row[:3] for row in m[:3]], [row[3] for row in m[:3]])
        shape = definitions[definition].moved(cq.Location(location_from_rigid_transform(transform)))
        occurrences.append(Occurrence(instance['instance_id'], shape, refs))
    return Model(snapshot['model_ref'], occurrences, tolerant=tolerant)
