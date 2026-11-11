import io
import json
from pathlib import Path
import zipfile
from urllib.parse import quote
import pytest
from thermal_drawings.settings import Settings
from thermal_drawings.api.auth import DevAuthenticator
from thermal_drawings.domain.errors import ServiceError
from thermal_drawings.storage.assets import controlled


def test_authentication_not_client_owner(service):
    service.call('GET', '/health', who=None, expected=401, headers={'X-Owner': 'alice'})
    service.call('GET', '/health', expected=401, headers={'Authorization': 'Bearer arbitrary'})
    service.call('GET', '/health', expected=403, headers={'Origin': 'https://evil.invalid'})
    service.call('GET', '/health', expected=403, headers={'Host': 'evil.invalid'})
    service.call('POST', '/projects', dict(name='spoof', module='paint', owner_id='bob'), expected=422)
    p = service.project()
    assert service.call('GET', '/projects/' + p, headers={'X-Owner': 'bob', 'X-Forwarded-For': '8.8.8.8'})[1]['owner_id'] == 'alice'
    service.call('GET', '/projects/' + p, who='bob', expected=404)


def test_dev_auth_cannot_be_public(service):
    settings = Settings.from_file(service.config)
    from dataclasses import replace
    for changes in ({'bind_host': '0.0.0.0'}, {'auth_mode': 'host'}, {'auth_mode': 'disabled'}, {'concurrency': 2}):
        with pytest.raises(ValueError):
            replace(settings, **changes).validate()
    class Fake:
        client = type('Client', (), {'host': '10.0.0.1'})()
        headers = {'host': '127.0.0.1', 'authorization': 'Bearer ' + service.tokens['alice']}
    with pytest.raises(ServiceError) as e:
        DevAuthenticator(settings).authenticate(Fake())
    assert e.value.status == 403


def test_session_project_and_module_isolation(service):
    p = service.project()
    binding = dict(session_id='a-session', module='paint', project_id=p, expected_revision='empty')
    service.call('PUT', '/sessions/a-session/binding', binding, who='other_session', expected=403)
    service.call('GET', '/sessions/a-session/binding', who='bob', expected=403)
    binding['session_id'] = 'b-session'
    service.call('PUT', '/sessions/b-session/binding', binding, who='bob', expected=404)
    service.call('POST', '/projects', dict(name='wrong module', module='blanket'), expected=403)
    # Same owner, another session still cannot write until explicitly bound.
    service.call('POST', f'/projects/{p}/assets', b'x', who='other_session', expected=403,
                 headers={'Content-Type': 'application/step', 'X-Filename': 'a.step'})


@pytest.mark.parametrize('name', ['../a.step', '/tmp/a.step', 'C:\\a.step', 'a%2f.step', 'a.zip', 'a..step', 'a.step/evil'])
def test_upload_paths_rejected(service, name):
    p = service.project()
    service.call('POST', f'/projects/{p}/assets', b'ISO-10303-21; END-ISO-10303-21;', expected=422,
                 headers={'Content-Type': 'application/step', 'X-Filename': name})
    assert not list((service.data / 'uploads').iterdir())


def test_percent_encoded_unicode_upload_filename(service):
    project = service.project()
    uploaded = service.call(
        'POST', f'/projects/{project}/assets',
        (Path(__file__).resolve().parents[2] / 'fixtures/synthetic/assembly-tree.step').read_bytes(), expected=201,
        headers={'Content-Type': 'application/step', 'X-Filename': quote('简化卫星.step')},
    )[1]
    assert uploaded['filename'] == '简化卫星.step'
    run = service.wait(service.submit_import(project, uploaded))
    assert run['state'] == 'succeeded'


def test_archives_truncated_and_oversize_rejected(service):
    p = service.project()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('../../escape.step', 'malicious')
    for data, status in [(stream.getvalue(), 422), (b'ISO-10303-21; HEADER;', 422), (b'x' * (1024 * 1024 + 1), 413)]:
        service.call('POST', f'/projects/{p}/assets', data, expected=status,
                     headers={'Content-Type': 'application/step', 'X-Filename': 'input.step'})
    assert not list((service.data / 'uploads').iterdir())
    assert not (service.directory / 'escape.step').exists()


def test_foreign_assets_imports_and_downloads(service):
    p = service.project()
    asset = service.upload(p)
    other = service.project('bob')
    service.call('GET', f'/projects/{p}/assets/{asset["id"]}', who='bob', expected=404)
    service.call('POST', f'/projects/{other}/imports', dict(asset_id=asset['id'], main_file=asset['filename'],
                 format_options={}, expected_revision='empty', idempotency_key='foreign'), who='bob', expected=404)
    own = service.project()
    service.call('GET', f'/projects/{own}/assets/{asset["id"]}', expected=404)


def test_symlink_storage_escape_rejected(tmp_path):
    root = tmp_path / 'root'; root.mkdir()
    (root / 'link').symlink_to(tmp_path, target_is_directory=True)
    for path in ('../escape', '/etc/passwd', 'link/secret', 'C:/secret', 'a\\secret'):
        with pytest.raises(ServiceError):
            controlled(root, path)


def test_artifact_permissions_and_integrity(service, imported):
    p, asset, revision, run = imported
    a = run['artifacts'][0]
    service.call('GET', '/artifacts/' + a['id'], who='bob', expected=404)
    service.call('GET', '/runs/' + run['id'], who='blanket', expected=404)
    service.call('POST', '/runs/' + run['id'] + '/cancel', who='bob', expected=404)
    content = service.call('GET', '/artifacts/' + a['id'], raw=True)[1]
    assert content and str(service.data).encode() not in json.dumps(run).encode()
    (service.data / a['relative_storage_path']).write_bytes(b'tampered')
    service.call('GET', '/artifacts/' + a['id'], expected=409)
