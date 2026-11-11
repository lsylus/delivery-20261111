def test_recommendations_follow_the_exact_model_across_engineering_revisions(service, imported):
    project, _, revision, _ = imported
    run = service.wait(service.operation(
        project, revision, 'paint.recommend', {'model_ref': revision['model_ref']}
    )['run_id'])
    assert run['state'] == 'succeeded'
    original = service.call('GET', f'/projects/{project}/paint-recommendations')[1]
    assert original['recommendations']['revision_id'] == revision['id']

    edited = service.edit(project, revision, {'note': 'same model, new engineering revision'})
    reused = service.call('GET', f'/projects/{project}/paint-recommendations')[1]
    assert reused['result_id'] == original['result_id']
    assert reused['recommendations']['revision_id'] == revision['id']
    assert reused['recommendations']['model_ref'] == edited['model_ref']

    replacement_asset = service.upload(project)
    replacement_run = service.wait(service.submit_import(project, replacement_asset, expected=edited['id']))
    assert replacement_run['state'] == 'succeeded'
    assert service.call('GET', f'/projects/{project}/paint-recommendations')[1] is None
