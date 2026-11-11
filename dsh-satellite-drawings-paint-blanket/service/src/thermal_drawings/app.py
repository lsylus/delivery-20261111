"""B06 private service. No legacy services, CAD imports, or identity inference in HTTP."""
from contextlib import asynccontextmanager
import json
import asyncio
import os
from pathlib import Path
import shutil
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from .settings import Settings
from .api.auth import DevAuthenticator
from .api.host_auth import HostAuthenticator, authorize_resource
from .domain.errors import ServiceError, require
from .domain.validation import validate, canonical
from .storage.repository import Repository, uid
from .storage.assets import filename, sha, controlled, check_step, sync_dir
from .runtime.queue import Queue


async def body(request, definition):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        require(size <= 1024 * 1024, 413, 'too_large', 'JSON request is too large')
        chunks.append(chunk)
    try:
        value = json.loads(b''.join(chunks))
    except (ValueError, UnicodeError):
        raise ServiceError(422, 'invalid_json', 'Invalid JSON') from None
    validate('runtime', value, definition)
    return value


def create_app(settings):
    settings.validate()
    auth = HostAuthenticator(settings) if settings.auth_mode == 'dsh-account' else DevAuthenticator(settings)
    repo = Repository(settings.data_root)

    @asynccontextmanager
    async def lifespan(app):
        queue = Queue(repo, settings)
        app.state.queue = queue
        queue.start()
        try:
            yield
        finally:
            queue.close()

    app = FastAPI(title='Satellite Drawings B06', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.repo = repo

    @app.middleware('http')
    async def authentication(request, call_next):
        try:
            if settings.auth_mode == 'dsh-account':
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    require(size <= settings.upload_limit, 413, 'too_large')
                    chunks.append(chunk)
                request._body = b''.join(chunks)
                request.state.principal = await asyncio.to_thread(auth.authenticate, request, request._body)
                await asyncio.to_thread(
                    authorize_resource,
                    repo,
                    request.state.principal,
                    request.method,
                    request.url.path,
                )
                if request.method == 'PUT' and request.url.path.endswith('/binding'):
                    try:
                        binding_value = json.loads(request._body)
                    except (ValueError, UnicodeError):
                        raise ServiceError(422, 'invalid_json', 'Invalid JSON') from None
                    if isinstance(binding_value, dict) and isinstance(binding_value.get('project_id'), str):
                        authorize_resource(
                            repo,
                            request.state.principal,
                            'GET',
                            '/api/v1/projects/' + binding_value['project_id'],
                        )
                if request.method == 'POST' and request.url.path == '/api/v1/projects':
                    try:
                        project_value = json.loads(request._body)
                    except (ValueError, UnicodeError):
                        raise ServiceError(422, 'invalid_json', 'Invalid JSON') from None
                    require(
                        isinstance(project_value, dict)
                        and str(project_value.get('name', '')).startswith('TEST-qmh-'),
                        422,
                        'test_project_prefix_required',
                    )
            else:
                request.state.principal = auth.authenticate(request)
            return await call_next(request)
        except ServiceError as error:
            return JSONResponse(error.error, status_code=error.status)

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        return JSONResponse(error.error, status_code=error.status)

    @app.get('/api/v1/health')
    def health():
        require(app.state.queue.thread.is_alive(), 503, 'queue_unavailable', 'Queue supervisor is not running')
        return {'status': 'ok'}

    @app.get('/api/v1/capabilities')
    def capabilities():
        return dict(implementation_stage='B13', auth_mode=settings.auth_mode, trusted_host='awaiting_platform_acceptance' if settings.auth_mode == 'dsh-account' else 'not_configured',
                    formats=['STEP-single-file'], operations=['model.import', 'engineering.rebind', 'geometry.analyze', 'blanket.detect_installation', 'blanket.generate', 'blanket.edit_shape', 'blanket.unfold', 'blanket.edit_seams', 'blanket.edit_fixed_points', 'engineering.save', 'engineering.restore', 'paint.recommend', 'paint.generate', 'paint.generate_batch', 'paint.edit_regions', 'drawing.edit_annotation', 'history.undo', 'history.redo'] + (['drawing.export'] if settings.converter_config else []),
                    unavailable=['ASM', 'PRT'] + ([] if settings.converter_config else ['DWG']),
                    concurrency=1, upload_limit_bytes=settings.upload_limit)

    @app.post('/api/v1/projects', status_code=201)
    async def projects(request: Request):
        value = await body(request, 'CreateProject')
        require(value['module'] == request.state.principal.module, 403)
        return repo.create(request.state.principal, value['name'])

    @app.get('/api/v1/projects/{project}')
    def project_get(project: str, request: Request):
        return repo.get_project(request.state.principal, project)

    @app.get('/api/v1/sessions/{session}/binding')
    def binding_get(session: str, request: Request):
        return repo.binding(request.state.principal, session)

    @app.put('/api/v1/sessions/{session}/binding')
    async def binding_put(session: str, request: Request):
        value = await body(request, 'SessionBinding')
        return repo.binding(request.state.principal, session, value)

    @app.post('/api/v1/projects/{project}/assets', status_code=201)
    async def assets(project: str, request: Request):
        principal = request.state.principal
        with repo.tx() as c:
            repo.bound(c, principal, project)
        name = filename(request.headers.get('x-filename'))
        require(request.headers.get('content-type', '').split(';')[0] in ('application/step', 'application/octet-stream'), message='Raw STEP upload required')
        id_ = uid()
        temp = repo.root / 'uploads' / id_
        size = 0
        dest = repo.root / 'assets' / id_ / name
        registered = False
        try:
            with temp.open('xb') as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    require(size <= settings.upload_limit, 413, 'too_large', 'Upload exceeds configured limit')
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
            check_step(temp)
            asset = dict(id=id_, filename=name, sha256=sha(temp), bytes=size, format='STEP', storage=f'assets/{id_}/{name}')
            dest.parent.mkdir(parents=True)
            os.replace(temp, dest)
            sync_dir(dest.parent)
            sync_dir(dest.parent.parent)
            with repo.tx() as c:
                repo.bound(c, principal, project)
                c.execute('INSERT INTO assets VALUES(?,?,?)', (id_, project, canonical(asset)))
            registered = True
            return {k: v for k, v in asset.items() if k != 'storage'}
        finally:
            temp.unlink(missing_ok=True)
            if not registered and dest.parent.exists():
                shutil.rmtree(dest.parent)

    @app.get('/api/v1/projects/{project}/assets/{asset_id}')
    def asset_get(project: str, asset_id: str, request: Request):
        with repo.tx() as c:
            asset = repo.asset(c, request.state.principal, project, asset_id)
        path = controlled(repo.root, asset['storage'])
        require(path.is_file() and sha(path) == asset['sha256'], 409, 'integrity_failed', 'Asset integrity check failed')
        return FileResponse(path, media_type='application/step', filename=asset['filename'])

    @app.post('/api/v1/projects/{project}/imports', status_code=202)
    async def imports(project: str, request: Request):
        value = await body(request, 'ImportRequest')
        require(not value['format_options'], 503, 'capability_unavailable', 'STEP format options are not implemented')
        filename(value['main_file'])
        run = repo.submit(request.state.principal, project, 'model.import', value['expected_revision'], value['idempotency_key'], value)
        return {'run_id': run['id']}

    @app.get('/api/v1/projects/{project}/models/{model_id}')
    def model_get(project: str, model_id: str, request: Request):
        with repo.tx() as c:
            model = repo.model(c, request.state.principal, project, model_id)
        return model

    @app.post('/api/v1/projects/{project}/revisions', status_code=201)
    async def revisions(project: str, request: Request):
        value = await body(request, 'RevisionRequest')
        return repo.edit(request.state.principal, project, value)

    @app.get('/api/v1/projects/{project}/revisions/{revision_id}')
    def revision_get(project: str, revision_id: str, request: Request):
        with repo.tx() as c:
            repo.project(c, request.state.principal, project)
            return repo.revision(c, project, request.state.principal.module, revision_id)

    @app.get('/api/v1/projects/{project}/paint-result')
    def result_get(project: str, request: Request):
        from .api.operations import paint_result
        principal = request.state.principal
        require(principal.module == 'paint', 403)
        with repo.tx() as c:
            p = repo.project(c, principal, project)
            head = repo.head(p, principal.module)
            return paint_result(repo, c, project, principal.module, head, optional=True)

    @app.get('/api/v1/projects/{project}/paint-recommendations')
    def recommendations_get(project: str, request: Request):
        from .api.operations import paint_recommendations
        principal = request.state.principal
        require(principal.module == 'paint', 403)
        with repo.tx() as c:
            p = repo.project(c, principal, project)
            return paint_recommendations(repo, c, project, principal.module, repo.head(p, principal.module), optional=True)

    @app.get('/api/v1/projects/{project}/paint-batch-result')
    def batch_result_get(project: str, request: Request):
        from .api.operations import paint_batch_result
        principal = request.state.principal
        require(principal.module == 'paint', 403)
        with repo.tx() as c:
            p = repo.project(c, principal, project)
            return paint_batch_result(repo, c, project, principal.module, repo.head(p, principal.module), optional=True)

    @app.get('/api/v1/projects/{project}/blanket-result')
    def blanket_result_get(project: str, request: Request):
        from .blanket.operations import current_result
        principal=request.state.principal
        require(principal.module=='blanket',403)
        with repo.tx() as c:
            p=repo.project(c,principal,project)
            return current_result(repo,c,project,repo.head(p,'blanket'),optional=True)

    @app.get('/api/v1/projects/{project}/blanket-net')
    def blanket_net_get(project: str, request: Request):
        from .blanket.net_operations import current_net
        principal=request.state.principal
        require(principal.module=='blanket',403)
        with repo.tx() as c:
            p=repo.bound(c,principal,project)
            return current_net(repo,c,project,repo.head(p,'blanket'),optional=True)

    @app.post('/api/v1/projects/{project}/operations', status_code=202)
    async def operations(project: str, request: Request):
        value = await body(request, 'OperationEnvelope')
        principal = request.state.principal
        require(value['project_id'] == project and value['module'] == principal.module, 403)
        require(value['operation'] in ('engineering.rebind', 'geometry.analyze', 'blanket.detect_installation', 'blanket.generate', 'blanket.edit_shape', 'blanket.unfold', 'blanket.edit_seams', 'blanket.edit_fixed_points', 'engineering.save', 'engineering.restore', 'paint.recommend', 'paint.generate', 'paint.generate_batch', 'paint.edit_regions', 'drawing.edit_annotation', 'drawing.export', 'history.undo', 'history.redo'), 503, 'capability_unavailable', 'Operation is not implemented')
        if value['operation']=='engineering.rebind':
            validate('complex',value['parameters'],'RebindInput')
        elif value['operation']=='geometry.analyze':
            validate('complex',value['parameters'],'AnalysisInput')
        elif value['operation']=='blanket.detect_installation':
            require(principal.module=='blanket',403)
        elif value['operation'] in ('blanket.generate', 'blanket.edit_shape'):
            require(principal.module == 'blanket',403)
            validate('blanket',value['parameters'], 'BlanketInput' if value['operation']=='blanket.generate' else 'EditShape')
        elif value['operation'] in ('blanket.unfold','blanket.edit_seams','blanket.edit_fixed_points'):
            require(principal.module=='blanket',403)
            validate('blanket',value['parameters'],{'blanket.unfold':'Unfold','blanket.edit_seams':'EditSeams','blanket.edit_fixed_points':'EditFixedPoints'}[value['operation']])
        elif value['operation'] in ('history.undo','history.redo') and principal.module=='blanket':
            require(value['parameters']=={},422)
        elif value['operation'] == 'paint.generate':
            require(principal.module == 'paint', 403)
            validate('paint', value['parameters'])
        elif value['operation'] == 'paint.recommend':
            require(principal.module == 'paint', 403)
            validate('paint', value['parameters'], 'PaintRecommendationInput')
        elif value['operation'] == 'paint.generate_batch':
            require(principal.module == 'paint', 403)
            validate('paint', value['parameters'], 'PaintBatchInput')
        elif value['operation'] == 'engineering.save':
            require(value['parameters'] == {}, message='engineering.save uses the persisted revision and takes no parameters')
        elif value['operation'] == 'engineering.restore':
            require(set(value['parameters']) == {'artifact_id'} and isinstance(value['parameters']['artifact_id'], str))
        else:
            require(principal.module == 'paint' or value['operation'] in ('drawing.export','drawing.edit_annotation'), 503, 'capability_unavailable')
            if value['operation'] == 'drawing.export':
                require(bool(settings.converter_config), 503, 'capability_unavailable', 'Draft DWG converter is not configured')
            from .paint.commands import validate_command
            validate_command(value['operation'], value['parameters'])
        run = repo.submit(principal, project, value['operation'], value['expected_revision'], value['idempotency_key'], value)
        return {'run_id': run['id']}

    @app.get('/api/v1/runs/{run_id}')
    def run_get(run_id: str, request: Request):
        return repo.get_run(request.state.principal, run_id)

    @app.post('/api/v1/runs/{run_id}/cancel', status_code=202)
    def run_cancel(run_id: str, request: Request):
        return repo.get_run(request.state.principal, run_id, cancel=True)

    @app.get('/api/v1/artifacts/{artifact_id}')
    def artifact_get(artifact_id: str, request: Request):
        with repo.tx() as c:
            artifact = repo.artifact(c, request.state.principal, artifact_id)['value']
        path = controlled(repo.root, artifact['relative_storage_path'])
        require(path.is_file() and path.stat().st_size == artifact['bytes'] and sha(path) == artifact['sha256'], 409, 'integrity_failed', 'Artifact integrity check failed')
        return FileResponse(path, media_type=artifact['mime_type'])

    return app
