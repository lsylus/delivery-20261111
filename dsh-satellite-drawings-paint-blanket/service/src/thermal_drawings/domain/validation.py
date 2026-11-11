"""Bundled schemas are checked against the workspace contract in acceptance tests."""
import hashlib
import json
from pathlib import Path
from functools import lru_cache
from jsonschema import Draft202012Validator, FormatChecker, ValidationError, validators
from referencing import Registry, Resource
from .errors import ServiceError


def unique_by(validator, key, instance, schema):
    """Project schema keyword: array object identifiers must be unique."""
    if not isinstance(instance, list):
        return
    seen = set()
    for item in instance:
        if isinstance(item, dict) and isinstance(item.get(key), str):
            if item[key] in seen:
                yield ValidationError(f'Duplicate {key}: {item[key]}')
            seen.add(item[key])


Draft202012Validator = validators.extend(Draft202012Validator, {'x-uniqueBy': unique_by}, version='satellite-drawings-2020-12')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@lru_cache
def validator(name, definition=None):
    schemas = [json.loads(p.read_text()) for p in (Path(__file__).parent / 'schemas').glob('*.json')]
    registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas)
    uri = f'https://satellite-drawings.invalid/contracts/{name}.schema.json'
    if definition:
        uri += '#/$defs/' + definition
    return Draft202012Validator({'$ref': uri}, registry=registry, format_checker=FormatChecker())


def validate(name, value, definition=None):
    try:
        canonical(value)
        validator(name, definition).validate(value)
    except (ValidationError, ValueError, TypeError):
        raise ServiceError(422, 'invalid_input', 'Payload does not satisfy the versioned contract') from None
