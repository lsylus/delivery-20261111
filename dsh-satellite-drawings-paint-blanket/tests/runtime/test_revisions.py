from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from thermal_drawings.domain.validation import validate


def test_immutable_revisions_and_compare_swap(service, imported):
    p, a, revision, run = imported
    def edit(i):
        return service.call('POST', f'/projects/{p}/revisions', dict(expected_revision=revision['id'], model_ref=revision['model_ref'],
                            parameters={'size': i}, selection=[], overrides=[]), expected=None)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(edit, [1, 2]))
    assert sorted(r[0] for r in results) == [201, 409]
    assert service.call('GET', f'/projects/{p}/revisions/{revision["id"]}')[1] == revision
    with sqlite3.connect(service.data / 'engineering.sqlite3') as c:
        import pytest
        with pytest.raises(sqlite3.IntegrityError):
            c.execute('UPDATE revisions SET body=? WHERE id=?', ('{}', revision['id']))


def test_cross_model_selection_and_unknown_fields(service, imported):
    p, a, revision, run = imported
    request = dict(expected_revision=revision['id'], model_ref=revision['model_ref'], parameters={}, selection=[], overrides=[], owner_id='bob')
    service.call('POST', f'/projects/{p}/revisions', request, expected=422)
    request.pop('owner_id'); request['model_ref'] = dict(revision['model_ref'], model_revision=2)
    service.call('POST', f'/projects/{p}/revisions', request, expected=409)
    request['model_ref'] = revision['model_ref']; request['parameters'] = {'bad': float('nan')}
    service.call('POST', f'/projects/{p}/revisions', request, expected=422)


def test_two_modules_share_source_but_restore_separate_state(service, imported):
    p, a, paint, run = imported
    paint = service.edit(p, paint, {'paint_only': 3})
    service.bind(p, 'blanket')
    blanket = service.call('POST', f'/projects/{p}/revisions', dict(expected_revision='empty', model_ref=paint['model_ref'],
                           parameters={'blanket_only': 15}, selection=[], overrides=[]), 'blanket', 201)[1]
    saved = service.wait(service.operation(p, paint)['run_id'])
    assert saved['state'] == 'succeeded', saved
    bundle_artifact = saved['artifacts'][0]
    bundle = json.loads(service.call('GET', '/artifacts/' + bundle_artifact['id'], raw=True)[1])
    validate('model', bundle, 'EngineeringBundle')
    assert bundle['construction_parameters']['parameters'] == {'paint_only': 3}
    assert bundle['source_manifest_refs'] == [a['id']]
    assert len(bundle['derived_shape_refs']) == 4
    service.call('GET', '/artifacts/' + bundle_artifact['id'], who='blanket', expected=404)
    service.call('GET', f'/projects/{p}/revisions/{paint["id"]}', who='blanket', expected=404)
    service.operation(p, blanket, 'engineering.restore', {'artifact_id': bundle_artifact['id']}, who='blanket', expected=404)
    edited = service.edit(p, paint, {'paint_only': 9})
    restored = service.wait(service.operation(p, edited, 'engineering.restore', {'artifact_id': bundle_artifact['id']})['run_id'])
    assert restored['state'] == 'succeeded', restored
    project = service.call('GET', '/projects/' + p)[1]
    new_revision = service.call('GET', f'/projects/{p}/revisions/{project["module_states"]["paint"]}')[1]
    assert new_revision['parameters'] == {'paint_only': 3}
    assert new_revision['id'] != paint['id'] and new_revision['parent_id'] == edited['id']
    assert project['module_states']['blanket'] == blanket['id']
    blanket_save = service.wait(service.operation(p, blanket, who='blanket')['run_id'], 'blanket')
    assert blanket_save['state'] == 'succeeded'
    blanket_edit = service.edit(p, blanket, {'blanket_only': 30}, who='blanket')
    blanket_restore = service.wait(service.operation(p, blanket_edit, 'engineering.restore',
                                   {'artifact_id': blanket_save['artifacts'][0]['id']}, who='blanket')['run_id'], 'blanket')
    assert blanket_restore['state'] == 'succeeded'
    project = service.call('GET', '/projects/' + p)[1]
    assert project['module_states']['paint'] == new_revision['id']
    restored_blanket = service.call('GET', f'/projects/{p}/revisions/{project["module_states"]["blanket"]}', who='blanket')[1]
    assert restored_blanket['parameters'] == {'blanket_only': 15}
    service.stop(); service.start()
    assert service.call('GET', '/projects/' + p)[1] == project
    assert service.call('GET', '/sessions/a-session/binding')[1]['project_id'] == p


def test_unconfigured_export_and_empty_history_fail_closed(service, imported):
    p, a, rev, run = imported
    assert service.operation(p, rev, 'history.undo', expected=409)['code'] == 'history_empty'
    service.operation(p, rev, 'drawing.export', {'result_id': 'unavailable', 'draft': True}, expected=503)
    cap = service.call('GET', '/capabilities')[1]
    assert cap['trusted_host'] == 'not_configured'
    assert 'ASM' in cap['unavailable'] and 'DWG' in cap['unavailable']


def test_exact_face_reference_required(service, imported):
    p, a, revision, run = imported
    artifact = next(a for a in run['artifacts'] if a['relative_storage_path'].endswith('/mesh-map.json'))
    face = json.loads(service.call('GET', '/artifacts/' + artifact['id'], raw=True)[1])['faces'][0]['face_ref']
    request = dict(expected_revision=revision['id'], model_ref=revision['model_ref'], parameters={}, selection=[face], overrides=[])
    new = service.call('POST', f'/projects/{p}/revisions', request, expected=201)[1]
    request['expected_revision'] = new['id']
    face['entity_id'] = 'fabricated'
    assert service.call('POST', f'/projects/{p}/revisions', request, expected=422)[1]['code'] == 'needs_reselection'


def test_restore_foreign_project_bundle_rejected(service, imported):
    p, a, revision, run = imported
    saved = service.wait(service.operation(p, revision)['run_id'])
    p2, a2, revision2, run2 = service.imported()
    service.operation(p2, revision2, 'engineering.restore', {'artifact_id': saved['artifacts'][0]['id']}, expected=404)


def test_restore_missing_geometry_keeps_last_valid_revision(service, imported):
    p, a, revision, run = imported
    saved = service.wait(service.operation(p, revision)['run_id'])
    edited = service.edit(p, revision, {'keep': 'last-valid'})
    shape = next(a for a in run['artifacts'] if a['format'] == 'BREP')
    (service.data / shape['relative_storage_path']).unlink()
    failed = service.wait(service.operation(p, edited, 'engineering.restore', {'artifact_id': saved['artifacts'][0]['id']})['run_id'])
    assert failed['state'] == 'failed' and failed['artifacts'] == []
    assert service.call('GET', '/projects/' + p)[1]['module_states']['paint'] == edited['id']
