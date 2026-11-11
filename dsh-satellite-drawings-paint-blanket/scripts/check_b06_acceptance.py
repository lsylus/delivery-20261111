"""Archive a real HTTP import/save/restore/restart and cleanup, including output bytes."""
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/evidence/B06'


def main():
    # Reuse the HTTP harness, never substitute service or worker behavior.
    spec = importlib.util.spec_from_file_location('b06_http_harness', ROOT / 'tests/runtime/http_harness.py')
    harness = importlib.util.module_from_spec(spec); spec.loader.exec_module(harness)
    record = dict(status='failed', resources_created=[], resources_cleaned=[], artifacts=[])
    service = None
    try:
        with tempfile.TemporaryDirectory(prefix='b06-acceptance-', dir=ROOT / 'work') as temp:
            folder = Path(temp)
            record['resources_created'].append(str(folder))
            service = harness.Service(folder / 'service')
            record['resources_created'].append('pid:' + str(service.process.pid))
            p, asset, revision, imported = service.imported()
            revision = service.edit(p, revision, {'paint_selection_policy': 'manual', 'saved_value': 3})
            service.bind(p, 'blanket')
            blanket = service.call('POST', f'/projects/{p}/revisions', dict(expected_revision='empty', model_ref=revision['model_ref'],
                                   parameters={'blanket_saved_value': 15}, selection=[], overrides=[]), 'blanket', 201)[1]
            save = service.wait(service.operation(p, revision)['run_id'])
            assert save['state'] == 'succeeded'
            changed = service.edit(p, revision, {'saved_value': 9})
            restore = service.wait(service.operation(p, changed, 'engineering.restore', {'artifact_id': save['artifacts'][0]['id']})['run_id'])
            assert restore['state'] == 'succeeded'
            state = service.call('GET', '/projects/' + p)[1]
            restored = service.call('GET', f'/projects/{p}/revisions/{state["module_states"]["paint"]}')[1]
            assert restored['parameters'] == revision['parameters']
            assert state['module_states']['blanket'] == blanket['id']
            blanket_save = service.wait(service.operation(p, blanket, who='blanket')['run_id'], 'blanket')
            blanket_edit = service.edit(p, blanket, {'blanket_saved_value': 30}, who='blanket')
            blanket_restore = service.wait(service.operation(p, blanket_edit, 'engineering.restore',
                                           {'artifact_id': blanket_save['artifacts'][0]['id']}, who='blanket')['run_id'], 'blanket')
            assert blanket_save['state'] == blanket_restore['state'] == 'succeeded'
            state = service.call('GET', '/projects/' + p)[1]
            restored_blanket = service.call('GET', f'/projects/{p}/revisions/{state["module_states"]["blanket"]}', who='blanket')[1]
            assert restored_blanket['parameters'] == blanket['parameters']
            assert state['module_states']['paint'] == restored['id']
            artifact_dir = OUT / 'artifacts'; artifact_dir.mkdir(exist_ok=True)
            for run in (imported, save, restore, blanket_save, blanket_restore):
                for a in run['artifacts']:
                    data = service.call('GET', a['download_url'].removeprefix('/api/v1'), who='blanket' if run['module'] == 'blanket' else 'alice', raw=True)[1]
                    assert hashlib.sha256(data).hexdigest() == a['sha256'] and len(data) == a['bytes']
                    relative = a['relative_storage_path'].split('/', 2)[2]
                    if run['module'] == 'blanket':
                        relative = 'blanket/' + relative
                    target = artifact_dir / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    record['artifacts'].append(dict(path=target.relative_to(ROOT).as_posix(), sha256=a['sha256'], bytes=a['bytes']))
            old_pid = service.process.pid
            service.stop(); service.start()
            record['resources_cleaned'].append('pid:' + str(old_pid))
            record['resources_created'].append('pid:' + str(service.process.pid))
            assert service.call('GET', '/projects/' + p)[1] == state
            assert service.call('GET', '/runs/' + imported['id'])[1] == imported
            record.update(project=state, imported_run=imported, save_run=save, restore_run=restore,
                          blanket_save_run=blanket_save, blanket_restore_run=blanket_restore, restored_blanket=restored_blanket,
                          restored_revision=restored, source=asset, ports=service.ports,
                          capabilities=service.call('GET', '/capabilities')[1], status='pass')
            last_pid = service.process.pid
            service.close(); service = None
            record['resources_cleaned'].append('pid:' + str(last_pid))
        record['resources_cleaned'].append(str(folder))
    except Exception as exc:
        record['error'] = repr(exc)
        raise
    finally:
        if service is not None:
            service.close()
        (OUT / 'acceptance.json').write_text(json.dumps(record, indent=2) + '\n')
        environment = dict(status='pass', python=sys.version, platform=platform.platform(), machine=platform.machine(),
                           packages={p: importlib.metadata.version(p) for p in ('fastapi', 'uvicorn', 'pytest', 'jsonschema', 'cadquery', 'cadquery-ocp')},
                           auth='dev-only; loopback ephemeral port; operator-provisioned opaque credentials',
                           resources='Private temporary data root, SQLite, supervisor and native processes cleaned')
        (OUT / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'artifacts': len(record['artifacts']), 'ports': record['ports']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
