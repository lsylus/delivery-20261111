import json
import os
import signal
import sqlite3
from pathlib import Path
from conftest import Service


def test_worker_crash_does_not_publish(service):
    p = service.project(); a = service.upload(p)
    id_ = service.submit_import(p, a)
    pid = service.native_pid(id_); os.kill(pid, signal.SIGKILL)
    run = service.wait(id_)
    assert run['state'] == 'failed' and run['error']['code'] == 'worker_failed'
    assert not run['artifacts'] and not (service.data / 'published' / id_).exists()
    assert service.wait(service.submit_import(p, a))['state'] == 'succeeded'


def test_service_crash_recovery_and_orphan_cleanup(service):
    p = service.project(); a = service.upload(p)
    id_ = service.submit_import(p, a)
    pid = service.native_pid(id_); os.kill(pid, signal.SIGSTOP)
    service.stop(crash=True)
    # Emulate a crash after atomic rename but before database commit.
    orphan = service.data / 'published' / id_; orphan.mkdir(exist_ok=True)
    (orphan / 'half.brep').write_bytes(b'partial')
    service.start()
    run = service.wait(id_)
    assert run['state'] == 'failed' and run['error']['code'] == 'service_restarted'
    assert run['artifacts'] == [] and not orphan.exists()
    if Path(f'/proc/{pid}/stat').exists():
        assert Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z'
    assert service.wait(service.submit_import(p, a))['state'] == 'succeeded'


def test_timeout_is_real_process_termination(tmp_path):
    service = Service(tmp_path / 'timeout', timeout=0.001)
    try:
        p = service.project(); a = service.upload(p)
        id_ = service.submit_import(p, a)
        run = service.wait(id_)
        assert run['state'] == 'failed' and run['error']['code'] == 'timeout'
        assert not run['artifacts']
        with sqlite3.connect(service.data / 'engineering.sqlite3') as c:
            pid = c.execute('SELECT pid FROM runs WHERE id=?', (id_,)).fetchone()[0]
        assert not Path(f'/proc/{pid}').exists()
    finally:
        service.close()


def test_queued_work_survives_restart(service):
    p = service.project(); a = service.upload(p)
    first = service.submit_import(p, a)
    pid = service.native_pid(first); os.kill(pid, signal.SIGSTOP)
    second = service.submit_import(p, a)
    assert service.call('GET', '/runs/' + second)[1]['state'] == 'queued'
    service.stop(crash=True); service.start()
    assert service.wait(first)['state'] == 'failed'
    assert service.wait(second)['state'] == 'succeeded'


def test_exclusive_supervisor_lock(service):
    from thermal_drawings.runtime.queue import Queue
    from thermal_drawings.storage.repository import Repository
    from thermal_drawings.settings import Settings
    import pytest
    with pytest.raises(BlockingIOError):
        Queue(Repository(service.data), Settings.from_file(service.config))


def test_cancel_requested_recovery_and_partial_output(service):
    p = service.project(); a = service.upload(p)
    id_ = service.submit_import(p, a)
    pid = service.native_pid(id_); os.kill(pid, signal.SIGSTOP)
    # Persist the cancellation before deliberately crashing the supervisor.
    service.stop(crash=True)
    with sqlite3.connect(service.data / 'engineering.sqlite3') as c:
        run = json.loads(c.execute('SELECT body FROM runs WHERE id=?', (id_,)).fetchone()[0])
        run['state'] = 'cancel_requested'
        c.execute('UPDATE runs SET state=?,body=? WHERE id=?', ('cancel_requested', json.dumps(run), id_))
    partial = service.data / 'staging' / id_; partial.mkdir(exist_ok=True)
    (partial / 'half.glb').write_bytes(b'partial')
    unregistered = service.data / 'assets' / 'unregistered'; unregistered.mkdir()
    (unregistered / 'half.step').write_bytes(b'partial')
    service.start()
    run = service.wait(id_)
    assert run['state'] == 'cancelled' and not run['artifacts']
    assert not partial.exists() and not unregistered.exists()
