import hashlib
import json
from pathlib import Path
from thermal_drawings.domain.validation import validate
from conftest import ROOT


def test_real_step_tree_brep_glb_and_face_map(service, imported):
    p, asset, revision, run = imported
    validate('run', run)
    validate('runtime', asset, 'Asset')
    validate('runtime', service.call('GET', '/capabilities')[1], 'Capabilities')
    validate('model', revision, 'EngineeringRevision')
    model = service.call('GET', f'/projects/{p}/models/{revision["model_ref"]["model_id"]}')[1]
    validate('runtime', model, 'ModelResponse')
    snapshot = model['snapshot']
    validate('model', snapshot, 'ModelSnapshot')
    assert len(snapshot['instances']) == 5
    assert len(snapshot['definitions']) == 4
    blobs = {a['relative_storage_path'].split('/')[-1]: service.call('GET', '/artifacts/' + a['id'], raw=True)[1] for a in run['artifacts']}
    assert blobs['model.glb'][:4] == b'glTF'
    assert len([k for k in blobs if k.endswith('.brep')]) == 4
    mapping = json.loads(blobs['mesh-map.json'])
    assert mapping['glb_sha256'] == hashlib.sha256(blobs['model.glb']).hexdigest()
    assert len(mapping['faces']) == 19
    assert all(f['face_ref']['model_id'] == revision['model_ref']['model_id'] for f in mapping['faces'])
    assert service.call('GET', f'/projects/{p}/assets/{asset["id"]}', raw=True)[1] == (ROOT / 'fixtures/synthetic/assembly-tree.step').read_bytes()
    assert not list((service.data / 'staging').iterdir())


def test_corrupt_step_never_publishes_demo(service):
    p = service.project()
    a = service.call('POST', f'/projects/{p}/assets', b'ISO-10303-21;\nHEADER; ENDSEC; DATA; garbage; ENDSEC; END-ISO-10303-21;',
                     expected=201, headers={'Content-Type': 'application/step', 'X-Filename': 'bad.step'})[1]
    run = service.wait(service.submit_import(p, a))
    assert run['state'] == 'failed' and run['artifacts'] == []
    assert service.call('GET', '/projects/' + p)[1]['module_states']['paint'] is None


def test_asset_mutation_detected_in_worker(service):
    p = service.project(); a = service.upload(p)
    path = service.data / 'assets' / a['id'] / a['filename']
    path.write_bytes(b'changed')
    run = service.wait(service.submit_import(p, a))
    assert run['state'] == 'failed' and not run['artifacts']


def test_contract_copies_and_no_legacy_runtime_imports():
    import thermal_drawings.domain.validation as validation
    for path in (ROOT / 'contracts').glob('*.schema.json'):
        assert path.read_bytes() == (Path(validation.__file__).parent / 'schemas' / path.name).read_bytes()
    import ast
    for path in (ROOT / 'service/src/thermal_drawings').rglob('*.py'):
        if '/drawing/' in str(path):
            continue
        tree = ast.parse(path.read_text())
        modules = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        modules += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(m == 'backend' or m.startswith('backend.') for m in modules)
