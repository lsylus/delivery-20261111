import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


class Service:
    def __init__(self, directory, timeout=60, upload_limit=1024 * 1024):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data = directory / 'data'
        self.data.mkdir(mode=0o700)
        self.tokens = {name: secrets.token_urlsafe(32) for name in ('alice', 'bob', 'other_session', 'blanket')}
        self.principals = {'alice': dict(owner='alice', session='a-session', module='paint'),
                           'bob': dict(owner='bob', session='b-session', module='paint'),
                           'other_session': dict(owner='alice', session='a-other', module='paint'),
                           'blanket': dict(owner='alice', session='a-blanket', module='blanket')}
        credentials = directory / 'credentials.json'
        credentials.write_text(json.dumps({hashlib.sha256(self.tokens[k].encode()).hexdigest(): v for k, v in self.principals.items()}))
        credentials.chmod(0o600)
        self.config = directory / 'config.json'
        self.config.write_text(json.dumps(dict(data_root=str(self.data), credentials_file=str(credentials),
                                             auth_mode='dev-only', timeout_s=timeout, upload_limit=upload_limit)))
        self.ready = directory / 'ready.json'
        self.log = (directory / 'service.log').open('a')
        self.process = None
        self.ports = []
        self.start()

    def start(self):
        self.ready.unlink(missing_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
        self.process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/serve_dev.py'), '--config', str(self.config), '--ready-file', str(self.ready)],
                                        cwd=self.directory, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError((self.directory / 'service.log').read_text())
            if self.ready.exists():
                value = json.loads(self.ready.read_text())
                self.port = value['port']
                self.url = f'http://127.0.0.1:{self.port}/api/v1'
                try:
                    if self.call('GET', '/health', expected=None)[0] == 200:
                        self.ports.append(self.port)
                        return
                except OSError:
                    pass
            time.sleep(0.03)
        raise AssertionError('Service startup timeout')

    def stop(self, crash=False):
        if self.process and self.process.poll() is None:
            self.process.kill() if crash else self.process.terminate()
            self.process.wait(timeout=15)

    def close(self):
        self.stop()
        self.log.close()
        for port in self.ports:
            with socket.socket() as s:
                assert s.connect_ex(('127.0.0.1', port)) != 0
        shutil.rmtree(self.directory)

    def call(self, method, path, data=None, who='alice', expected=200, headers=None, raw=False):
        hdr = {'Authorization': 'Bearer ' + self.tokens[who]} if who else {}
        if data is not None and not isinstance(data, bytes):
            data = json.dumps(data).encode()
            hdr['Content-Type'] = 'application/json'
        hdr.update(headers or {})
        req = urllib.request.Request(self.url + path, data=data, headers=hdr, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            response = e
        payload = response.read()
        code = response.status
        response.close()
        if not raw:
            payload = json.loads(payload)
        if expected is not None:
            assert code == expected, (code, payload)
        return code, payload

    def project(self, who='alice'):
        module = self.principals[who]['module']
        p = self.call('POST', '/projects', dict(name='B06 test', module=module), who, 201)[1]
        self.bind(p['id'], who)
        return p['id']

    def bind(self, project, who='alice', expected='empty'):
        principal = self.principals[who]
        return self.call('PUT', '/sessions/' + principal['session'] + '/binding',
                         dict(session_id=principal['session'], module=principal['module'], project_id=project, expected_revision=expected), who)[1]

    def upload(self, project, fixture='assembly-tree.step', who='alice'):
        return self.call('POST', f'/projects/{project}/assets', (ROOT / 'fixtures/synthetic' / fixture).read_bytes(), who, 201,
                         {'Content-Type': 'application/step', 'X-Filename': fixture})[1]

    def submit_import(self, project, asset, expected='empty', key=None, who='alice'):
        return self.call('POST', f'/projects/{project}/imports', dict(asset_id=asset['id'], main_file=asset['filename'], format_options={},
                         expected_revision=expected, idempotency_key=key or secrets.token_hex(12)), who, 202)[1]['run_id']

    def wait(self, id_, who='alice'):
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            run = self.call('GET', '/runs/' + id_, who=who)[1]
            if run['state'] in ('succeeded', 'failed', 'cancelled'):
                return run
            time.sleep(0.03)
        raise AssertionError('Job did not terminate')

    def native_pid(self, id_):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with sqlite3.connect(self.data / 'engineering.sqlite3') as c:
                row = c.execute('SELECT pid FROM runs WHERE id=?', (id_,)).fetchone()
            if row and row[0]:
                return row[0]
            time.sleep(0.005)
        raise AssertionError('Worker not spawned')

    def imported(self, who='alice'):
        project = self.project(who)
        asset = self.upload(project, who=who)
        run = self.wait(self.submit_import(project, asset, who=who), who)
        assert run['state'] == 'succeeded', (run, list((self.data / 'jobs').glob('*.log')))
        head = self.call('GET', '/projects/' + project, who=who)[1]['module_states'][self.principals[who]['module']]
        revision = self.call('GET', f'/projects/{project}/revisions/{head}', who=who)[1]
        return project, asset, revision, run

    def edit(self, p, rev, params, who='alice', expected=201):
        return self.call('POST', f'/projects/{p}/revisions', dict(expected_revision=rev['id'], model_ref=rev['model_ref'],
                         parameters=params, selection=rev['selection'], overrides=rev['overrides']), who, expected)[1]

    def operation(self, p, rev, operation='engineering.save', parameters=None, who='alice', key=None, expected=202):
        return self.call('POST', f'/projects/{p}/operations', dict(schema_version=1, module=self.principals[who]['module'],
                         operation=operation, project_id=p, model_ref=rev['model_ref'], expected_revision=rev['id'],
                         selection_refs=rev['selection'], parameters=parameters or {}, overrides=rev['overrides'],
                         idempotency_key=key or secrets.token_hex(12)), who, expected)[1]
