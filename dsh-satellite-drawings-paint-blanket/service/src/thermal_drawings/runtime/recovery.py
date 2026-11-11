"""Recovery runs while holding the exclusive data-root supervisor lock."""
import json
import os
import shutil
import signal
import time
from pathlib import Path
from ..storage.repository import unpack


def process_start(pid):
    try:
        # comm can contain spaces and parentheses; fields after the final ')' start at 3.
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def kill_owned(pid, start):
    if pid and start and process_start(pid) == start:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5
        while process_start(pid) == start:
            try:
                if Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                    return
            except FileNotFoundError:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError('Worker termination could not be confirmed')
            time.sleep(0.01)


def recover(repo):
    with repo.tx() as c:
        for row in c.execute("SELECT * FROM runs WHERE state IN ('running','cancel_requested')").fetchall():
            kill_owned(row['pid'], row['start'])
            run = unpack(row)
            cancelled = run['state'] == 'cancel_requested'
            run.update(state='cancelled' if cancelled else 'failed', artifacts=[],
                       error=None if cancelled else dict(code='service_restarted', message='Worker interrupted by service restart',
                                                        stage='recovery', retryable=True, evidence_refs=[]))
            repo.put_run(c, run)
        registered = {row['id'] for row in c.execute("SELECT id FROM runs WHERE state='succeeded'")}
        for directory in ('staging', 'jobs', 'uploads'):
            path = repo.root / directory
            path.mkdir(exist_ok=True)
            for child in path.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        published = repo.root / 'published'
        published.mkdir(exist_ok=True)
        for child in published.iterdir():
            if child.name not in registered:
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        assets = repo.root / 'assets'
        assets.mkdir(exist_ok=True)
        asset_ids = {row['id'] for row in c.execute('SELECT id FROM assets')}
        for child in assets.iterdir():
            if child.name not in asset_ids:
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
