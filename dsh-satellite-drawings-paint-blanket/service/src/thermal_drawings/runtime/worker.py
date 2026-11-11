"""Short-lived subprocess. Parent death kills this process; no HTTP or DB writes."""
from thermal_drawings.domain.acceptance import usable
import ctypes
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import signal
import sys
from ..domain.validation import canonical, validate
from ..storage.assets import controlled, sha, sync_dir


def _regular_model_scope(parameters):
    if parameters.get('envelope_policy') not in ('regular_box_v1', 'regular_cylinder_v1', 'feature_composite_v1'):
        return None
    instances = set(parameters['target_instances']) | set(parameters.get('excluded_instances', []))
    # Keep an explicitly selected installation occurrence available so the
    # regular policy can report its existing target-scope validation error.
    if parameters.get('installation_face'):
        instances.add(parameters['installation_face']['instance_id'])
    return instances


def main():
    parent = int(sys.argv[2])
    # Linux PR_SET_PDEATHSIG closes the spawn/before-pid-registration crash window.
    if ctypes.CDLL(None).prctl(1, signal.SIGKILL) != 0 or os.getppid() != parent:
        return 2
    job = json.loads(Path(sys.argv[1]).read_text())
    memory = job['memory_limit_mb'] * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root, output = Path(job['root']), Path(job['output'])
    run, payload = job['run'], job['payload']
    output.mkdir()
    if run['operation'] == 'model.import':
        from ..importers.step import import_step
        snapshot = import_step(root, run, payload, output)
        validate('model', snapshot, 'ModelSnapshot')
        result = dict(model_ref=snapshot['model_ref'])
    elif run['operation']=='engineering.rebind':
        from ..paint.assets import load_model
        from ..domain.revision_transfer import compute
        transfer=compute(load_model(root,payload['rebind_model']),load_model(root,payload['model']),
                         payload['rebind_source'],payload['revision'],payload['rebind_id'],run['module'],output)
        result=dict(rebinding_status=transfer['status'])
    elif run['operation']=='geometry.analyze':
        from ..paint.assets import load_model
        from ..domain.complex_analysis import compute
        parameters=payload['request']['parameters']
        analysis=compute(load_model(root,payload['model'],instance_ids={parameters['face_ref']['instance_id']}),payload['revision'],parameters,run['module'],output)
        validate('complex',analysis,'AnalysisResult')
        (output/'complex-analysis.json').write_text(canonical(analysis))
        result={}
    elif run['module']=='blanket' and run['operation']=='blanket.detect_installation':
        from ..paint.assets import load_model
        from ..blanket.installation import detect
        parameters=payload['request']['parameters']
        detection=detect(load_model(root,payload['model'],exclude_reference_occurrences=True),
                         parameters['target_instances'],parameters['excluded_instances'],
                         parameters['maximum_gap_mm'])
        detection.update(revision_id=payload['revision']['id'],model_ref=payload['revision']['model_ref'],
                         target_instances=parameters['target_instances'],excluded_instances=parameters['excluded_instances'])
        (output/'installation-detection.json').write_text(canonical(detection))
        result=dict(installation_detection_status=detection['status'])
    elif run['module']=='paint' and run['operation']=='paint.recommend':
        from ..paint.assets import load_model
        from ..paint.recommendations import recommend
        model = load_model(root, payload['model'], tolerant=True)
        names = {instance['instance_id']: instance['name'] for instance in payload['model']['snapshot']['instances']}
        recommendations = recommend(model, payload['revision']['id'], names)
        validate('paint', recommendations, 'PaintRecommendationResult')
        (output/'paint-recommendations.json').write_text(canonical(recommendations))
        result = dict(recommendation_status=recommendations['status'])
    elif run['module']=='paint' and run['operation']=='paint.generate_batch':
        from ..paint.assets import load_model
        from ..paint.batch import generate_batch
        revision = payload['revision']
        batch = generate_batch(revision['parameters'], load_model(root, payload['model'], tolerant=True,
                               exclude_reference_occurrences=True), revision['id'], output=output)
        (output/'paint-batch-result.json').write_text(canonical(batch))
        result = dict(paint_batch_status=batch['status'])
    elif run['module']=='paint' and run['operation'] in ('paint.generate', 'paint.edit_regions', 'drawing.edit_annotation'):
        from ..paint.assets import load_model
        from ..paint.pipeline import generate
        model = load_model(root, payload['model'], exclude_reference_occurrences=True)
        from ..drawing.document_edits import apply_edits
        revision = payload.get('target_revision', payload['revision'])
        paint = apply_edits(generate(revision['parameters'], model, revision['id'],output=output), revision)
        (output / 'paint-result.json').write_text(canonical(paint))
        if paint['drawing_document'] is not None:
            (output / 'drawing.json').write_text(canonical(paint['drawing_document']))
        result = dict(paint_status=paint['status'])
    elif run['module']=='blanket' and run['operation'] in ('blanket.generate', 'blanket.edit_shape', 'blanket.unfold', 'blanket.edit_seams', 'blanket.edit_fixed_points', 'drawing.edit_annotation'):
        from ..paint.assets import load_model
        from ..blanket.pipeline import generate
        from ..blanket.selection import BlanketError
        from ..blanket.panels import NetError
        from ..blanket.net_operations import rebuild_net
        revision=payload.get('target_revision',payload['revision'])
        try:
            blanket=generate(revision['parameters'],load_model(root,payload['model'],instance_ids=_regular_model_scope(revision['parameters'])),revision['id'],output,payload.get('baseline'))
            net=rebuild_net(blanket,revision,output) if usable(blanket) or blanket['parameters'].get('envelope_policy')=='feature_composite_v1' else None
            result=dict(blanket_status=blanket['status'],net_status=net['status'] if net else None)
        except NetError as error:
            result=dict(blanket_error=str(error),net_diagnostic=error.diagnostic)
            (output/'blanket-diagnostic.json').write_text(canonical(result))
        except BlanketError as error:
            result=dict(blanket_error=str(error))
            (output/'blanket-diagnostic.json').write_text(canonical(result))
    elif run['operation'] == 'drawing.export':
        from ..drawing.export_pipeline import export_batch, export_draft
        if payload.get('paint_batch') is not None:
            export_batch(payload['paint_batch'], output, job['converter_config'])
        else:
            export_draft(payload.get('drawing_result',payload.get('paint')), output, job['converter_config'], preview=payload['request']['parameters'].get('preview', False))
        result = {}
    elif run['operation'] == 'engineering.save':
        revision, model = payload['revision'], payload['model']
        bundle = dict(schema_version=1,
                      source_manifest_refs=[model['snapshot']['source_manifest']['asset_id']],
                      derived_shape_refs=[a['id'] for a in model['artifacts'] if a['format'] == 'BREP'] + [a['id'] for a in payload.get('blanket_artifacts',[])],
                      construction_parameters={'module': run['module'], 'parameters': revision['parameters'],
                                               'model_ref': revision['model_ref'], 'paint_result': payload.get('paint'), 'blanket_result': payload.get('blanket')},
                      cut_edges=[], seams=[], fixed_points=[], drawing_document=payload['paint']['drawing_document'] if payload.get('paint') else None,
                      revisions=payload['history'], current_revision=revision['id'], rebuilder_version='b10-state-v1' if payload.get('blanket') else 'b09-state-v1' if payload.get('paint') else 'b06-state-v1')
        if payload.get('net'):
            net=payload['net'];bundle['construction_parameters']['net_result']=net
            bundle.update(rebuilder_version='b11-state-v1',cut_edges=[s['id'] for s in net['seams'] if s['kind']=='cut'],seams=net['seams'],fixed_points=[{k:p[k] for k in ('id','panel_id','uv_mm','position3d','mapping_ref','status')} for p in net['fixed_points']],drawing_document=net['drawing_document'])
        validate('model', bundle, 'EngineeringBundle')
        (output / 'engineering.json').write_text(canonical(bundle))
        result = {}
    elif run['operation'] == 'engineering.restore':
        a = payload['bundle_artifact']
        path = controlled(root, a['relative_storage_path'])
        if sha(path) != a['sha256']:
            raise ValueError('bundle integrity')
        bundle = json.loads(path.read_text())
        validate('model', bundle, 'EngineeringBundle')
        if bundle['rebuilder_version'] not in ('b06-state-v1', 'b09-state-v1', 'b10-state-v1', 'b11-state-v1') or bundle['construction_parameters']['module'] != run['module']:
            raise ValueError('bundle module/rebuilder mismatch')
        revision = next(r for r in bundle['revisions'] if r['id'] == bundle['current_revision'])
        if revision['model_ref']['project_id'] != run['project_id']:
            raise ValueError('foreign bundle')
        model, source = payload['restore_model'], payload['restore_asset']
        if revision['model_ref'] != model['snapshot']['model_ref'] or bundle['source_manifest_refs'] != [source['id']]:
            raise ValueError('bundle source mismatch')
        if sha(controlled(root, source['storage'])) != source['sha256']:
            raise ValueError('bundle source integrity')
        for derived in model['artifacts']:
            path = controlled(root, derived['relative_storage_path'])
            if path.stat().st_size != derived['bytes'] or sha(path) != derived['sha256']:
                raise ValueError('bundle derived geometry integrity')
        (output / 'restored.json').write_text(canonical(revision))
        paint = bundle['construction_parameters'].get('paint_result')
        if paint is not None:
            from ..drawing.document_edits import rebind
            if paint['model_ref'] != revision['model_ref'] or paint['revision_id'] != revision['id'] or paint['drawing_document'] != bundle['drawing_document']:
                raise ValueError('bundle drawing/result mismatch')
            paint = rebind(paint, payload['restored_id'])
            validate('paint', paint, 'PaintResult')
            (output/'paint-result.json').write_text(canonical(paint))
            (output/'drawing.json').write_text(canonical(paint['drawing_document']))
        blanket=bundle['construction_parameters'].get('blanket_result')
        if blanket is not None:
            from ..paint.assets import load_model
            from ..blanket.pipeline import generate
            if run['module']!='blanket' or bundle['rebuilder_version'] not in ('b10-state-v1','b11-state-v1') or blanket['parameters']!=revision['parameters'] or blanket['model_ref']!=revision['model_ref'] or blanket['revision_id']!=revision['id']:
                raise ValueError('bundle blanket mismatch')
            expected_refs=[a['id'] for a in model['artifacts'] if a['format']=='BREP']+[a['id'] for a in payload['restore_blanket_artifacts']]
            if bundle['derived_shape_refs']!=expected_refs:
                raise ValueError('bundle derived reference mismatch')
            for artifact in payload['restore_blanket_artifacts']:
                p=controlled(root,artifact['relative_storage_path'])
                if not p.is_file() or sha(p)!=artifact['sha256'] or p.stat().st_size!=artifact['bytes']:
                    raise ValueError('bundle blanket artifact integrity')
            rebuilt=generate(revision['parameters'],load_model(root,model),payload['restored_id'],output,blanket['baseline'])
            if not usable(rebuilt) or rebuilt['baseline']!=blanket['baseline']:
                raise ValueError('bundle blanket reconstruction failed')
            if bundle['rebuilder_version']=='b11-state-v1':
                from ..blanket.net_operations import rebuild_net
                saved_net=bundle['construction_parameters']['net_result']
                if saved_net['revision_id']!=revision['id'] or saved_net['drawing_document']!=bundle['drawing_document'] or [{k:p[k] for k in ('id','panel_id','uv_mm','position3d','mapping_ref','status')} for p in saved_net['fixed_points']]!=bundle['fixed_points'] or saved_net['seams']!=bundle['seams']:
                    raise ValueError('bundle net mismatch')
                net=rebuild_net(rebuilt,dict(revision,id=payload['restored_id']),output)
                if net is None or not usable(net) or [p['id'] for p in net['fixed_points']] != [p['id'] for p in saved_net['fixed_points']]:
                    raise ValueError('bundle net reconstruction failed')
        result = dict(restore=revision)
    else:
        raise ValueError('unsupported worker operation')
    files = []
    for path in sorted(output.rglob('*')):
        if path.is_file():
            with path.open('rb') as f:
                os.fsync(f.fileno())
            files.append(dict(path=path.relative_to(output).as_posix(), sha256=sha(path), bytes=path.stat().st_size))
    result.update(files=files, tool_versions={p: importlib.metadata.version(p) for p in ('thermal-drawings-service', 'satellite-geometry-core', 'cadquery', 'cadquery-ocp')})
    (output / 'result.json').write_text(canonical(result))
    with (output / 'result.json').open('rb') as f:
        os.fsync(f.fileno())
    for path in output.rglob('*'):
        if path.is_dir():
            sync_dir(path)
    sync_dir(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
