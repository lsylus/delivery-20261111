"""Versioned structural and cross-field validation; no CAD/business computation."""
import hashlib
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker, ValidationError, validators
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://satellite-drawings.invalid/contracts/'


def unique_by(validator, key, instance, schema):
    """Project schema keyword, shared semantics with the packaged validator."""
    if not isinstance(instance, list):
        return
    seen = set()
    for item in instance:
        if isinstance(item, dict) and isinstance(item.get(key), str):
            if item[key] in seen:
                yield ValidationError(f'Duplicate {key}: {item[key]}')
            seen.add(item[key])


Draft202012Validator = validators.extend(Draft202012Validator, {'x-uniqueBy': unique_by}, version='satellite-drawings-2020-12')

def digest_files(files):
    """SHA256 of canonical UTF-8 JSON of path-sorted {relative_path,sha256,bytes}."""
    records = sorted(files, key=lambda f: f['relative_path'])
    return hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def validator(name, definition=None, root=ROOT):
    resources=[]
    schemas={}
    for path in (root/'contracts').glob('*.schema.json'):
        s=json.loads(path.read_text()); Draft202012Validator.check_schema(s)
        resources.append((s['$id'], Resource.from_contents(s))); schemas[path.stem.removesuffix('.schema')]=s
    schema=schemas[name] if definition is None else {'$ref':f'{BASE}{name}.schema.json#/$defs/{definition}'}
    return Draft202012Validator(schema, registry=Registry().with_resources(resources), format_checker=FormatChecker())

def fail(message): raise ValidationError(message)

def validate(name, value, definition=None):
    validator(name, definition).validate(value)
    if name=='mesh-map' and definition is None:
        for item in [*value['faces'],*value.get('unrenderable_faces',[])]:
            if any(item['face_ref'][k]!=v for k,v in value['model_ref'].items()):
                fail('mesh face reference belongs to another model revision')
        ranges={}
        for entry in value['faces']:
            key=(entry['node'],entry['mesh'],entry['primitive'])
            start=entry['triangle_start'];end=start+entry['triangle_count']
            ranges.setdefault(key,[]).append((start,end))
        for spans in ranges.values():
            spans.sort()
            if any(current[0]<previous[1] for previous,current in zip(spans,spans[1:])):
                fail('overlapping mesh primitive triangle map')
    if name=='summary' and value['status']=='passed':
        counts=value['tests']
        if not counts['required'] or counts['passed']!=counts['required'] or counts['failed'] or counts['skipped_required']:fail('passed summary requires all real tests passing')
        if not value['commands'] or any(c['exit_code'] for c in value['commands']):fail('passed summary requires successful actual commands')
        if not value['checks'] or any(c['status']!='pass' for c in value['checks']):fail('passed summary requires all checks')
        if not value['artifacts']:fail('passed summary requires hashed artifacts')
    def walk(v):
        if isinstance(v,float) and not math.isfinite(v): fail('non-finite number')
        if isinstance(v,list):
            for item in v: walk(item)
        if not isinstance(v,dict): return
        if {'x_axis','y_axis','z_axis','origin'} <= v.keys():
            axes=[v[k] for k in ('x_axis','y_axis','z_axis')]
            for i in range(3):
                for j in range(3):
                    if abs(sum(a*b for a,b in zip(axes[i],axes[j]))-(i==j))>1e-9: fail('frame axes must be orthonormal')
            x,y,z=axes
            cross=[x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
            if any(abs(a-b)>1e-9 for a,b in zip(cross,z)): fail('frame must be right handed')
        if v.get('kind')=='rigid' and 'matrix' in v:
            m=v['matrix']
            if any(abs(a-b)>1e-9 for a,b in zip(m[3],[0,0,0,1])): fail('invalid homogeneous matrix')
            walk({'origin':[m[i][3] for i in range(3)],'x_axis':[m[i][0] for i in range(3)],'y_axis':[m[i][1] for i in range(3)],'z_axis':[m[i][2] for i in range(3)]})
        if 'model_ref' in v:
            model=v['model_ref']
            if 'project_id' in v and v['project_id'] != model['project_id']: fail('project mismatch')
            for key in ('selection_refs','target_face_refs','included_faces','excluded_faces','entity_refs','selection','cut_edges','fold_edges'):
                for e in v.get(key,[]):
                    if any(e[k]!=model[k] for k in model): fail('reference belongs to another model revision')
        if 'files' in v and 'assembly_digest' in v:
            paths=[f['relative_path'] for f in v['files']]
            if len(paths)!=len(set(paths)): fail('duplicate source path')
            if v['main_file'] not in paths: fail('main_file not in manifest')
            if digest_files(v['files']) != v['assembly_digest']: fail('assembly digest mismatch')
        if 'definitions' in v and 'instances' in v:
            definitions=[d['id'] for d in v['definitions']]; instances=[i['instance_id'] for i in v['instances']]
            if len(set(definitions))!=len(definitions) or len(set(instances))!=len(instances): fail('duplicate definition/instance ID')
            parents={i['instance_id']:i['parent_instance_id'] for i in v['instances']}
            for i in v['instances']:
                if i['definition_id'] not in definitions: fail('missing definition')
                seen=set(); parent=i['instance_id']
                while parent is not None:
                    if parent in seen or parent not in parents: fail('cyclic or missing instance parent')
                    seen.add(parent);parent=parents[parent]
        if 'operation' in v and 'parameters' in v:
            target={'paint.generate':'paint','blanket.generate':'blanket'}.get(v['operation'])
            if target:
                validate(target,v['parameters'])
                if v['parameters']['model_ref'] != v['model_ref']: fail('operation parameters model mismatch')
            if v['operation']=='paint.generate_batch':
                validate('paint',v['parameters'],'PaintBatchInput')
                if v['parameters']['model_ref'] != v['model_ref']: fail('operation parameters model mismatch')
            if v['operation']=='paint.recommend':
                validate('paint',v['parameters'],'PaintRecommendationInput')
                if v['parameters']['model_ref'] != v['model_ref']: fail('operation parameters model mismatch')
        for item in v.values(): walk(item)
    walk(value)
