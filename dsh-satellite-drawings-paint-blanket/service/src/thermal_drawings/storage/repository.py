"""SQLite is the authority for identity bindings, immutable revisions and job leases."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
import uuid
from ..domain.errors import require, ServiceError
from ..domain.validation import canonical, fingerprint, validate


def uid():
    return uuid.uuid4().hex


def unpack(row):
    return json.loads(row['body'])


class Repository:
    def __init__(self, root):
        self.root = root
        self.db = root / 'engineering.sqlite3'
        with self.tx() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS host_project_access(project TEXT,owner TEXT,can_read INTEGER NOT NULL,can_write INTEGER NOT NULL,PRIMARY KEY(project,owner));
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,owner TEXT NOT NULL,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY,project TEXT NOT NULL,module TEXT NOT NULL,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,project TEXT NOT NULL,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY,project TEXT NOT NULL,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bindings(owner TEXT,session TEXT,module TEXT,body TEXT NOT NULL,PRIMARY KEY(owner,session,module));
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,project TEXT NOT NULL,module TEXT NOT NULL,key TEXT NOT NULL,
                request_hash TEXT NOT NULL,state TEXT NOT NULL,lease TEXT,pid INTEGER,start TEXT,body TEXT NOT NULL,payload TEXT NOT NULL,
                UNIQUE(project,module,key));
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,project TEXT NOT NULL,module TEXT NOT NULL,shared INTEGER NOT NULL,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS redo(project TEXT,module TEXT,body TEXT,PRIMARY KEY(project,module));
            CREATE TABLE IF NOT EXISTS results(project TEXT,module TEXT,revision TEXT,run TEXT,PRIMARY KEY(project,module));
            CREATE TRIGGER IF NOT EXISTS revisions_immutable BEFORE UPDATE ON revisions BEGIN SELECT RAISE(ABORT,'immutable revision'); END;
            CREATE TRIGGER IF NOT EXISTS revisions_no_delete BEFORE DELETE ON revisions BEGIN SELECT RAISE(ABORT,'immutable revision'); END;
            ''')

    @contextmanager
    def tx(self):
        c = sqlite3.connect(self.db, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=FULL')
        c.execute('BEGIN IMMEDIATE')
        try:
            yield c
            if c.in_transaction:
                c.commit()
        except BaseException:
            if c.in_transaction:
                c.rollback()
            raise
        finally:
            c.close()

    def project(self, c, principal, project_id):
        row = c.execute('SELECT * FROM projects WHERE id=? AND owner=?', (project_id, principal.owner)).fetchone()
        require(row is not None, 404, 'not_found', 'Project is not visible')
        return unpack(row)

    def create(self, principal, name):
        p = dict(id=uid(), owner_id=principal.owner, name=name,
                 module_states={'paint': None, 'blanket': None}, created_at=datetime.now(timezone.utc).isoformat())
        with self.tx() as c:
            c.execute('INSERT INTO projects VALUES(?,?,?)', (p['id'], principal.owner, canonical(p)))
        return p

    def get_project(self, principal, id_):
        with self.tx() as c:
            return self.project(c, principal, id_)

    def head(self, p, module):
        return p['module_states'][module] or 'empty'

    def expected(self, p, module, expected):
        require(self.head(p, module) == expected, 409, 'revision_conflict', 'Current revision differs from expected_revision')

    def binding(self, principal, session, value=None):
        require(session == principal.session, 403, 'session_forbidden', 'Session does not match authenticated identity')
        with self.tx() as c:
            if value is not None:
                validate('operation', value, 'SessionBinding')
                require(value['session_id'] == session and value['module'] == principal.module, 403)
                p = self.project(c, principal, value['project_id'])
                self.expected(p, principal.module, value['expected_revision'])
                c.execute('INSERT OR REPLACE INTO bindings VALUES(?,?,?,?)',
                          (principal.owner, session, principal.module, canonical(value)))
            row = c.execute('SELECT body FROM bindings WHERE owner=? AND session=? AND module=?',
                            (principal.owner, session, principal.module)).fetchone()
            require(row is not None, 404, 'not_found', 'Session is not bound')
            return unpack(row)

    def bound(self, c, principal, project):
        p = self.project(c, principal, project)
        row = c.execute('SELECT body FROM bindings WHERE owner=? AND session=? AND module=?',
                        (principal.owner, principal.session, principal.module)).fetchone()
        require(row is not None and unpack(row)['project_id'] == project, 403, 'binding_required', 'Bind the authenticated session to this project first')
        return p

    def asset(self, c, principal, project, id_):
        self.project(c, principal, project)
        row = c.execute('SELECT body FROM assets WHERE id=? AND project=?', (id_, project)).fetchone()
        require(row is not None, 404, 'not_found', 'Asset is not visible')
        return unpack(row)

    def model(self, c, principal, project, id_):
        self.project(c, principal, project)
        row = c.execute('SELECT body FROM models WHERE id=? AND project=?', (id_, project)).fetchone()
        require(row is not None, 404, 'not_found', 'Model is not visible')
        return unpack(row)

    def revision(self, c, project, module, id_):
        row = c.execute('SELECT body FROM revisions WHERE id=? AND project=? AND module=?', (id_, project, module)).fetchone()
        require(row is not None, 404, 'not_found', 'Revision is not visible in this module')
        return unpack(row)

    def make_revision(self, c, project, module, parent, model_ref, data, revision_id=None):
        revision = dict(id=revision_id or uid(), parent_id=None if parent == 'empty' else parent, model_ref=model_ref,
                        parameters=data.get('parameters', {}), selection=data.get('selection', []),
                        overrides=data.get('overrides', []), document_edits=data.get('document_edits', []))
        require(all(all(e.get(k) == v for k, v in model_ref.items()) for e in revision['selection']), message='Selection belongs to another model revision')
        revision['input_fingerprint'] = fingerprint({k: v for k, v in revision.items() if k not in ('id', 'parent_id')})
        validate('model', revision, 'EngineeringRevision')
        c.execute('INSERT INTO revisions VALUES(?,?,?,?)', (revision['id'], project, module, canonical(revision)))
        return revision

    def move_head(self, c, p, module, revision, clear_redo=True):
        if clear_redo:
            c.execute('DELETE FROM redo WHERE project=? AND module=?', (p['id'], module))
        p['module_states'][module] = revision['id']
        c.execute('UPDATE projects SET body=? WHERE id=?', (canonical(p), p['id']))
        c.execute('DELETE FROM results WHERE project=? AND module=?', (p['id'], module))

    def edit(self, principal, project, value):
        with self.tx() as c:
            p = self.bound(c, principal, project)
            self.expected(p, principal.module, value['expected_revision'])
            ref = value['model_ref']
            model = self.model(c, principal, project, ref['model_id'])
            require(model['snapshot']['model_ref'] == ref, 409, 'model_conflict', 'Model reference is not current')
            if value['selection']:
                from .assets import controlled, sha
                artifact = next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('/mesh-map.json'))
                path = controlled(self.root, artifact['relative_storage_path'])
                require(sha(path) == artifact['sha256'], 409, 'integrity_failed', 'Mesh mapping integrity failed')
                known = [f['face_ref'] for f in json.loads(path.read_text())['faces']]
                require(all(e in known for e in value['selection']), 422, 'needs_reselection', 'Only exact current mesh-map face references are supported')
            require(not value.get('document_edits'), 422, 'use_command', 'Use version-bound editing operations')
            if value['expected_revision'] != 'empty':
                previous = self.revision(c, project, principal.module, value['expected_revision'])
                if previous['document_edits']:
                    require(previous['model_ref'] == ref and previous['selection'] == value['selection'], 409, 'needs_reselection', 'Existing manual edits cannot be rebound to different faces')
                    value = dict(value, document_edits=previous['document_edits'])
            revision = self.make_revision(c, project, principal.module, value['expected_revision'], ref, value)
            self.move_head(c, p, principal.module, revision)
            return revision

    def submit(self, principal, project, operation, expected, key, request):
        with self.tx() as c:
            p = self.bound(c, principal, project)
            digest = fingerprint(dict(operation=operation, expected=expected, request=request))
            row = c.execute('SELECT * FROM runs WHERE project=? AND module=? AND key=?', (project, principal.module, key)).fetchone()
            if row is not None:
                require(row['request_hash'] == digest, 409, 'idempotency_conflict', 'Key already used with different input')
                return unpack(row)
            self.expected(p, principal.module, expected)
            payload = dict(request=request)
            if operation == 'model.import':
                asset = self.asset(c, principal, project, request['asset_id'])
                require(request['main_file'] == asset['filename'], message='main_file must equal the uploaded basename')
                payload.update(asset=asset, model_id=uid())
                input_fp = fingerprint({'expected': expected, 'asset': asset['sha256']})
            else:
                revision = self.revision(c, project, principal.module, expected)
                require(request['model_ref'] == revision['model_ref'], 409, 'model_conflict', 'Operation model differs from revision')
                require(request['selection_refs'] == revision['selection'] and request['overrides'] == revision['overrides'], 409, 'unsaved_edits', 'Save revision edits before submitting an operation')
                payload['revision'] = revision
                if operation in ('paint.generate', 'paint.generate_batch'):
                    require(request['parameters'] == revision['parameters'], 409, 'unsaved_edits', 'Persist paint parameters before generation')
                    require(request['parameters']['model_ref'] == revision['model_ref'] and
                            request['parameters']['target_face_refs'] == revision['selection'] and
                            request['parameters']['overrides'] == revision['overrides'], 409, 'unsaved_edits', 'Paint input must match revision selection and overrides')
                    if operation == 'paint.generate_batch':
                        flattened = [ref for group in request['parameters']['target_face_groups'] for ref in group['target_face_refs']]
                        require(len(flattened) == len({canonical(ref) for ref in flattened}) and flattened == revision['selection'],
                                409, 'unsaved_edits', 'Batch groups must partition the exact persisted selection')
                if operation == 'paint.recommend':
                    require(request['parameters']['model_ref'] == revision['model_ref'], 409, 'model_conflict')
                history = [revision]
                while history[-1]['parent_id'] is not None:
                    history.append(self.revision(c, project, principal.module, history[-1]['parent_id']))
                payload['history'] = history
                input_fp = revision['input_fingerprint']
                model = self.model(c, principal, project, revision['model_ref']['model_id'])
                payload['model'] = model
                if operation == 'engineering.restore':
                    artifact = self.artifact(c, principal, request['parameters']['artifact_id'])
                    require(artifact['project'] == project and artifact['module'] == principal.module and artifact['value']['role'] == 'engineering_bundle', 404)
                    payload['bundle_artifact'] = artifact['value']
                    saved = c.execute('SELECT payload FROM runs WHERE id=?', (artifact['value']['run_id'],)).fetchone()
                    payload['restore_model'] = json.loads(saved['payload'])['model']
                    payload['restore_blanket_artifacts'] = json.loads(saved['payload']).get('blanket_artifacts', [])
                    source_id = payload['restore_model']['snapshot']['source_manifest']['asset_id']
                    payload['restore_asset'] = self.asset(c, principal, project, source_id)
                from ..api.operations import prepare
                prepare(self, c, p, principal, operation, request, payload)
            run = dict(schema_version=1, id=uid(), project_id=project, module=principal.module, operation=operation,
                       input_revision=expected, input_fingerprint=input_fp, idempotency_key=key,
                       state='queued', progress=0, worker=None, tool_versions={}, artifacts=[], checks=[], error=None)
            c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,NULL,NULL,NULL,?,?)',
                      (run['id'], project, principal.module, key, digest, 'queued', canonical(run), canonical(payload)))
            if operation in ('history.undo', 'history.redo'):
                from ..api.operations import history
                history(self, c, p, principal, operation, revision, run)
            return run

    def get_run(self, principal, id_, cancel=False):
        with self.tx() as c:
            row = c.execute('SELECT * FROM runs WHERE id=?', (id_,)).fetchone()
            require(row is not None, 404)
            self.project(c, principal, row['project'])
            require(row['module'] == principal.module, 404)
            run = unpack(row)
            if cancel:
                self.bound(c, principal, row['project'])
                if run['state'] in ('queued', 'running'):
                    run['state'] = 'cancel_requested'
                    self.put_run(c, run)
            return run

    def put_run(self, c, run):
        c.execute('UPDATE runs SET state=?,body=? WHERE id=?', (run['state'], canonical(run), run['id']))

    def artifact(self, c, principal, id_):
        row = c.execute('SELECT * FROM artifacts WHERE id=?', (id_,)).fetchone()
        require(row is not None, 404)
        self.project(c, principal, row['project'])
        require(row['shared'] or row['module'] == principal.module, 404)
        return dict(project=row['project'], module=row['module'], value=unpack(row))
