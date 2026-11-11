from concurrent.futures import ThreadPoolExecutor
import os
import signal
import time


def test_concurrent_idempotency_and_input_conflict(service):
    p = service.project(); a = service.upload(p)
    def submit(_):
        return service.submit_import(p, a, key='same-key')
    with ThreadPoolExecutor(4) as pool:
        ids = list(pool.map(submit, range(4)))
    assert len(set(ids)) == 1
    service.call('POST', f'/projects/{p}/imports', dict(asset_id=a['id'], main_file=a['filename'], format_options={},
                 expected_revision='different', idempotency_key='same-key'), expected=409)
    assert service.wait(ids[0])['state'] == 'succeeded'
    assert submit(0) == ids[0]  # retry after head advanced must still deduplicate


def test_cancel_requires_worker_termination(service):
    p = service.project(); a = service.upload(p)
    id_ = service.submit_import(p, a)
    pid = service.native_pid(id_)
    os.kill(pid, signal.SIGSTOP)
    reply = service.call('POST', '/runs/' + id_ + '/cancel', expected=202)[1]
    assert reply['state'] == 'cancel_requested' and reply['artifacts'] == []
    final = service.wait(id_)
    assert final['state'] == 'cancelled' and final['artifacts'] == []
    assert not os.path.exists('/proc/' + str(pid))
    assert not (service.data / 'published' / id_).exists()


def test_late_result_does_not_replace_new_revision(service, imported):
    p, a, rev, first = imported
    id_ = service.submit_import(p, a, expected=rev['id'])
    pid = service.native_pid(id_); os.kill(pid, signal.SIGSTOP)
    new = service.edit(p, rev, {'kept': True})
    os.kill(pid, signal.SIGCONT)
    late = service.wait(id_)
    assert late['state'] == 'succeeded'
    assert late['checks'][0]['observed']['current'] is False
    assert service.call('GET', '/projects/' + p)[1]['module_states']['paint'] == new['id']
    assert len(late['artifacts']) == len(first['artifacts'])


def test_cancel_publish_race_is_atomic(service):
    p = service.project(); a = service.upload(p)
    id_ = service.submit_import(p, a)
    service.call('POST', '/runs/' + id_ + '/cancel', expected=202)
    run = service.wait(id_)
    assert run['state'] in ('cancelled', 'succeeded')
    if run['state'] == 'cancelled':
        assert run['artifacts'] == []
        assert not (service.data / 'published' / id_).exists()
    else:
        assert len(run['artifacts']) == 7


def test_rejected_lease_and_corrupt_output_cannot_publish(service, imported, tmp_path):
    import json
    import shutil
    import pytest
    from thermal_drawings.runtime.publication import publish
    from thermal_drawings.storage.repository import Repository
    from thermal_drawings.domain.errors import ServiceError
    p, a, rev, run = imported
    output = tmp_path / 'result'
    shutil.copytree(service.data / 'published' / run['id'], output)
    repo = Repository(service.data)
    before = service.call('GET', '/projects/' + p)[1]
    with pytest.raises(ServiceError) as error:
        publish(repo, run['id'], 'expired-lease', output)
    assert error.value.error['code'] == 'lease_lost'
    # Only the top-level supervisor manifest is special. Native tools may
    # legitimately provide a nested JSON result, which must still be indexed.
    import hashlib
    nested=output/'native'/'result.json';nested.parent.mkdir();nested.write_text('{"ok":true}')
    manifest=json.loads((output/'result.json').read_text())
    manifest['files'].append(dict(path='native/result.json',sha256=hashlib.sha256(nested.read_bytes()).hexdigest(),bytes=nested.stat().st_size))
    (output/'result.json').write_text(json.dumps(manifest))
    with pytest.raises(ServiceError) as error:
        publish(repo, run['id'], 'expired-lease', output)
    assert error.value.error['code']=='lease_lost'
    extra=output/'native'/'late-profile.json';extra.write_text('{}')
    with pytest.raises(ServiceError) as error:
        publish(repo, run['id'], 'expired-lease', output)
    assert 'native/late-profile.json' in error.value.error['message']
    extra.unlink()
    (output / 'model.glb').write_bytes(b'partial')
    with pytest.raises(ServiceError):
        publish(repo, run['id'], run['worker'], output)
    assert service.call('GET', '/projects/' + p)[1] == before
    assert service.call('GET', '/runs/' + run['id'])[1] == run


def test_queue_cancels_process_group(tmp_path, monkeypatch):
    import subprocess
    import sys
    import threading
    from pathlib import Path
    from thermal_drawings.runtime.queue import Queue
    from thermal_drawings.storage.repository import Repository
    from thermal_drawings.api.auth import Principal
    from thermal_drawings.settings import Settings
    root = tmp_path / 'group'; root.mkdir()
    repo = Repository(root)
    principal = Principal('owner', 'session', 'paint')
    p = repo.create(principal, 'group cancellation')
    repo.binding(principal, 'session', dict(session_id='session', module='paint', project_id=p['id'], expected_revision='empty'))
    with repo.tx() as c:
        import json
        c.execute('INSERT INTO assets VALUES(?,?,?)', ('asset', p['id'], json.dumps(dict(id='asset', filename='input.step', sha256='0'*64))))
    run = repo.submit(principal, p['id'], 'model.import', 'empty', 'key', dict(asset_id='asset', main_file='input.step'))
    queue = Queue(repo, Settings(root, tmp_path / 'unused'))
    original = subprocess.Popen
    child_file = root / 'child.pid'
    code = "import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(120)"
    def injected(args, **kwargs):
        return original([sys.executable, '-c', code, str(child_file)], **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', injected)
    thread = threading.Thread(target=queue.once)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not child_file.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert child_file.exists()
        pid = int(child_file.read_text())
        assert repo.get_run(principal, run['id'], cancel=True)['state'] == 'cancel_requested'
        thread.join(10)
        assert not thread.is_alive()
        assert repo.get_run(principal, run['id'])['state'] == 'cancelled'
        if Path(f'/proc/{pid}/stat').exists():
            assert Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z'
    finally:
        queue.stop.set(); thread.join(10); queue.close()
