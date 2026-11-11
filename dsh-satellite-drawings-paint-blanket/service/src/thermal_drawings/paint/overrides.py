"""Explicit revision-scoped classification; uncertain rebinding is invalid."""
from .selection import PaintError


def resolve_overrides(values, model):
    result = {}
    ids = set()
    for value in values:
        if value['id'] in ids:
            raise PaintError('duplicate_override_id', 'PaintOverride.id must be unique across all FaceRefs')
        ids.add(value['id'])
        ref = value['face_ref']
        model.resolve(ref)
        if value['model_revision'] != model.model_ref['model_revision'] or not value['reason'].strip():
            raise PaintError('needs_reselection', 'Stale override or empty reason')
        key = (ref['instance_id'], ref['entity_id'])
        if key in result:
            raise PaintError('ambiguous_override', 'Conflicting classifications for one face')
        result[key] = value
    return result


def classification(ref, values):
    return values.get((ref['instance_id'], ref['entity_id']))
