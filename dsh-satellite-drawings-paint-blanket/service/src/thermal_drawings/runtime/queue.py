"""One durable queue, one native process at a time, with a fenced publication lease."""
import fcntl
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from ..storage.repository import uid, unpack
from ..domain.validation import canonical
from .publication import publish
from .recovery import recover, process_start, kill_owned


class Queue:
    def __init__(self, repo, settings):
        self.repo, self.settings = repo, settings
        self.stop = threading.Event()
        self.lock = (repo.root / 'supervisor.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.lock.close()
            raise
        recover(repo)
        self.thread = threading.Thread(target=self.loop, name='drawing-queue', daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread.ident:
            self.thread.join()
        self.lock.close()

    def finish(self, id_, state, code=None):
        with self.repo.tx() as c:
            row = c.execute('SELECT body FROM runs WHERE id=?', (id_,)).fetchone()
            run = unpack(row)
            if run['state'] == 'succeeded':
                return
            run.update(state=state, artifacts=[], error=None if state == 'cancelled' else
                       dict(code=code or 'worker_failed', message='Isolated worker did not produce a publishable result',
                            stage='worker', retryable=True, evidence_refs=[]))
            self.repo.put_run(c, run)

    def once(self):
        with self.repo.tx() as c:
            row = c.execute("SELECT * FROM runs WHERE state IN ('queued','cancel_requested') ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                return False
            run = unpack(row)
            if run['state'] == 'cancel_requested':
                run['state'] = 'cancelled'
                self.repo.put_run(c, run)
                return True
            lease = uid()
            run.update(state='running', worker=lease)
            self.repo.put_run(c, run)
            c.execute('UPDATE runs SET lease=? WHERE id=?', (lease, run['id']))
            payload = json.loads(row['payload'])
        output = self.repo.root / 'staging' / run['id']
        job = self.repo.root / 'jobs' / (run['id'] + '.json')
        log = self.repo.root / 'jobs' / (run['id'] + '.log')
        job.write_text(canonical(dict(root=str(self.repo.root), output=str(output), run=run, payload=payload,
                                     memory_limit_mb=self.settings.memory_limit_mb, converter_config=self.settings.converter_config)))
        process = None
        try:
            env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
            env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
            with log.open('w') as f:
                process = subprocess.Popen([sys.executable, '-I', '-m', 'thermal_drawings.runtime.worker', str(job), str(os.getpid())],
                                           cwd=self.repo.root, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
                start = process_start(process.pid)
                with self.repo.tx() as c:
                    c.execute('UPDATE runs SET pid=?,start=? WHERE id=? AND lease=?', (process.pid, start, run['id'], lease))
                deadline = time.monotonic() + self.settings.timeout_s
                reason = None
                while process.poll() is None:
                    with self.repo.tx() as c:
                        state = c.execute('SELECT state FROM runs WHERE id=?', (run['id'],)).fetchone()[0]
                    if state == 'cancel_requested' or self.stop.is_set() or time.monotonic() > deadline:
                        reason = 'cancelled' if state == 'cancel_requested' else 'service_shutdown' if self.stop.is_set() else 'timeout'
                        kill_owned(process.pid, start)
                        break
                    self.stop.wait(0.03)
                process.wait()
                # Parent is reaped before cancellation acknowledgement. Kill remaining group members too.
                try:
                    os.killpg(process.pid, 9)
                except ProcessLookupError:
                    pass
                with self.repo.tx() as c:
                    state = c.execute('SELECT state FROM runs WHERE id=?', (run['id'],)).fetchone()[0]
                if state == 'cancel_requested' or reason == 'cancelled':
                    self.finish(run['id'], 'cancelled')
                elif reason or process.returncode:
                    self.finish(run['id'], 'failed', reason or 'worker_failed')
                else:
                    publish(self.repo, run['id'], lease, output)
        except Exception:
            logging.exception('Publication failed for run %s',run['id'])
            with self.repo.tx() as c:
                state = c.execute('SELECT state FROM runs WHERE id=?', (run['id'],)).fetchone()[0]
            self.finish(run['id'], 'cancelled' if state == 'cancel_requested' else 'failed', 'publication_failed')
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            if output.exists():
                shutil.rmtree(output)
            with self.repo.tx() as c:
                success = c.execute('SELECT state FROM runs WHERE id=?', (run['id'],)).fetchone()[0] == 'succeeded'
            final = self.repo.root / 'published' / run['id']
            if not success and final.exists():
                shutil.rmtree(final)
            job.unlink(missing_ok=True)
        return True

    def loop(self):
        while not self.stop.is_set():
            if not self.once():
                self.stop.wait(0.05)
