"""Filesystem durability precedes the single SQLite publication transaction."""
from thermal_drawings.domain.acceptance import usable
import json
import os
import zipfile
from ..domain.validation import validate, canonical
from ..domain.errors import require
from ..storage.assets import controlled, sha, sync_dir
from ..storage.repository import uid, unpack


def reviewable_limit_preview(value):
    """A cover may be inspected when only its cutting-piece cap fails.

    This does not make the candidate usable for nets or exports. Geometric
    failures and every other failed requirement retain the normal rejection.
    """
    policy=value.get('parameters',{}).get('envelope_policy')
    if (policy not in ('regular_box_v1','regular_cylinder_v1','feature_composite_v1')
            or value.get('candidate_editable') is not True or value.get('status')!='failed'):
        return False
    summary=value.get('manufacturing_summary',{})
    if (summary.get('requirements_unmet')!=['piece_limit_exceeded']
            or not isinstance(summary.get('pieces_per_layer'),int)
            or not isinstance(summary.get('piece_limit'),int)
            or summary['pieces_per_layer']<=summary['piece_limit']):
        return False
    checks=value.get('checks',[])
    by_id={c['id']:c for c in checks}
    return (len(by_id)==len(checks) and {'coverage','topology','piece_limit','volume_ratio','unfolding'}<=set(by_id)
            and [c['id'] for c in checks if c['status']=='fail']==['piece_limit']
            and by_id['coverage']['status']=='pass' and by_id['topology']['status']=='pass'
            and all(c['status']=='pass' or c['id']=='piece_limit' and c['status']=='fail'
                    or c['id']=='unfolding' and c['status']=='not_run'
                    or policy=='feature_composite_v1' and c['id']=='feature_interfaces' and c['status']=='needs_review'
                    for c in checks))


def reviewable_feature_net_preview(net, cover):
    """Publish a complete, technically valid over-limit net for inspection only."""
    if (cover.get('parameters',{}).get('envelope_policy')!='feature_composite_v1'
            or not reviewable_limit_preview(cover)
            or net.get('revision_id')!=cover.get('revision_id')
            or net.get('cover_baseline_id')!=cover.get('baseline',{}).get('id')
            or net.get('diagnostics') or net.get('foldback',{}).get('status')!='pass'):
        return False
    counts=net.get('manufacturing_summary',{})
    if (counts.get('pieces_per_layer')!=len(net.get('pieces',[]))
            or counts.get('piece_limit')!=cover['manufacturing_summary']['piece_limit']):
        return False
    # Export/edit/save routes still require usable(), which rejects this net.
    return reviewable_limit_preview(dict(net,parameters=cover['parameters']))


def publish(repo, run_id, lease, output):
    result = json.loads((output / 'result.json').read_text())
    files = result['files']
    require(files and len({f['path'] for f in files}) == len(files))
    actual = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file() and p != output/'result.json'}
    expected = {f['path'] for f in files}
    require(actual == expected, message='Incomplete output manifest: missing='+str(sorted(expected-actual))+' unexpected='+str(sorted(actual-expected)))
    require(not any(p.is_symlink() for p in output.rglob('*')))
    for f in files:
        path = controlled(output, f['path'])
        require(path.is_file() and path.stat().st_size == f['bytes'] and sha(path) == f['sha256'], message='Output integrity failed')
    with repo.tx() as c:
        row = c.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        require(row is not None and row['lease'] == lease and row['state'] == 'running', 409, 'lease_lost', 'Worker no longer owns publication')
        run, payload = unpack(row), json.loads(row['payload'])
        p = unpack(c.execute('SELECT body FROM projects WHERE id=?', (run['project_id'],)).fetchone())
        current = repo.head(p, run['module']) == run['input_revision']
        if run['input_revision'] != 'empty' and run['operation'] != 'model.import':
            revision = repo.revision(c, p['id'], run['module'], run['input_revision'])
            require(revision['input_fingerprint'] == run['input_fingerprint'], 409)
        if run['operation'] == 'model.import':
            snapshot = json.loads((output / 'snapshot.json').read_text())
            validate('model', snapshot, 'ModelSnapshot')
            mapping = json.loads((output / 'mesh-map.json').read_text())
            validate('mesh-map', mapping)
            require(mapping['model_ref'] == snapshot['model_ref'])
            require(mapping['glb_sha256'] == sha(output / 'model.glb'))
            require(all(all(face['face_ref'][k] == v for k, v in snapshot['model_ref'].items()) for face in mapping['faces']))
            require((output / 'model.glb').read_bytes()[:4] == b'glTF')
            require(all(controlled(output, d['shape_asset']).is_file() for d in snapshot['definitions']))
            revision = repo.make_revision(c, p['id'], run['module'], run['input_revision'], snapshot['model_ref'], {})
        elif run['operation']=='engineering.rebind':
            transfer=json.loads((output/'rebind-analysis.json').read_text())
            require(transfer['source_revision']==payload['rebind_source']['id'] and transfer['target_revision']==revision['id'])
            require(transfer['source_model_ref']==payload['rebind_source']['model_ref'] and transfer['target_model_ref']==revision['model_ref'])
            if transfer['status']=='valid':
                candidate=transfer['candidate']
                require(candidate['id']==payload['rebind_id'] and candidate['parent_id']==revision['id'] and candidate['model_ref']==revision['model_ref'])
                revision=repo.make_revision(c,p['id'],run['module'],revision['id'],revision['model_ref'],candidate,payload['rebind_id'])
            else:
                current=False
                # A failed rebind may have computed candidate geometry; only
                # the historical report is published, never a usable candidate.
                require(not transfer.get('candidate'))
        elif run['operation']=='geometry.analyze':
            analysis=json.loads((output/'complex-analysis.json').read_text())
            validate('complex',analysis,'AnalysisResult')
            require(analysis['revision_id']==revision['id'] and analysis['model_ref']==revision['model_ref'])
            require(analysis['module']==run['module'] and analysis['source_ref']==payload['request']['parameters']['face_ref'])
        elif run['module']=='blanket' and run['operation']=='blanket.detect_installation':
            detection=json.loads((output/'installation-detection.json').read_text())
            parameters=payload['request']['parameters'];candidates=detection.get('candidates')
            require(detection.get('revision_id')==revision['id'] and detection.get('model_ref')==revision['model_ref'])
            require(detection.get('target_instances')==parameters['target_instances']
                    and detection.get('excluded_instances')==parameters['excluded_instances']
                    and detection.get('maximum_gap_mm')==parameters['maximum_gap_mm'])
            require(detection.get('status') in ('unique','none','ambiguous') and isinstance(candidates,list))
            require((detection['status']=='unique' and len(candidates)==1)
                    or (detection['status']=='none' and not candidates)
                    or (detection['status']=='ambiguous' and len(candidates)>1))
            for candidate in candidates:
                require(set(('target_face_ref','support_face_ref','gap_mm','contact_area_mm2'))<=set(candidate))
                require(candidate['target_face_ref']['instance_id'] in parameters['target_instances'])
                require(candidate['support_face_ref']['instance_id'] not in set(parameters['target_instances'])|set(parameters['excluded_instances']))
                require(isinstance(candidate['gap_mm'],(int,float)) and 0<=candidate['gap_mm']<=parameters['maximum_gap_mm'])
                require(isinstance(candidate['contact_area_mm2'],(int,float)) and candidate['contact_area_mm2']>0)
        elif run['module']=='paint' and run['operation']=='paint.recommend':
            recommendations=json.loads((output/'paint-recommendations.json').read_text())
            validate('paint',recommendations,'PaintRecommendationResult')
            require(recommendations['revision_id']==revision['id'] and recommendations['model_ref']==revision['model_ref'])
        elif run['module']=='paint' and run['operation']=='paint.generate_batch':
            batch=json.loads((output/'paint-batch-result.json').read_text())
            validate('paint',batch,'PaintBatchResult')
            require(batch['revision_id']==revision['id'] and batch['model_ref']==revision['model_ref'])
            if batch['status']=='failed':
                run.update(state='failed',artifacts=[],checks=batch['checks'],tool_versions=result['tool_versions'],
                           error=dict(code='paint_batch_failed',message='No selected surface group produced an editable drawing',stage='paint_batch',retryable=False,evidence_refs=[]))
                validate('run',run);repo.put_run(c,run);return
        elif run['module']=='paint' and run['operation'] in ('paint.generate', 'paint.edit_regions', 'drawing.edit_annotation'):
            paint = json.loads((output / 'paint-result.json').read_text())
            validate('paint', paint, 'PaintResult')
            revision = payload.get('target_revision', revision)
            require(paint['revision_id'] == revision['id'] and paint['model_ref'] == revision['model_ref'])
            if paint['status'] == 'failed':
                run.update(state='failed', artifacts=[], checks=paint['checks'], tool_versions=result['tool_versions'],
                           error=dict(code='paint_failed', message='Paint checks failed; previous result preserved',
                                      stage='paint', retryable=False, evidence_refs=[]))
                validate('run', run)
                repo.put_run(c, run)
                return
            if paint['drawing_document'] is not None:
                require(json.loads((output / 'drawing.json').read_text()) == paint['drawing_document'])
            current = current and usable(paint)
        elif run['module']=='blanket' and run['operation'] in ('blanket.generate', 'blanket.edit_shape', 'blanket.unfold', 'blanket.edit_seams', 'blanket.edit_fixed_points', 'drawing.edit_annotation'):
            if result.get('blanket_error'):
                run.update(state='failed',artifacts=[],tool_versions=result['tool_versions'],error=dict(code='blanket_input_or_geometry',message=result['blanket_error'],stage='blanket',retryable=False,evidence_refs=[]))
                if result.get('net_diagnostic'):
                    run['checks']=[dict(id='net_input',status='fail',scope_refs=[],observed=result['net_diagnostic'],limit=None,units='mm',algorithm_version='b11-planar-v1',evidence_refs=[],reason=result['blanket_error'])]
                validate('run',run);repo.put_run(c,run);return
            blanket=json.loads((output/'blanket-result.json').read_text())
            validate('blanket',blanket,'BlanketResult')
            revision=payload.get('target_revision',revision)
            require(blanket['revision_id']==revision['id'] and blanket['model_ref']==revision['model_ref'] and blanket['parameters']==revision['parameters'])
            limit_preview=run['operation']=='blanket.generate' and reviewable_limit_preview(blanket)
            if blanket['status']=='failed' and not limit_preview:
                run.update(state='failed',artifacts=[],checks=blanket['checks'],tool_versions=result['tool_versions'],error=dict(code='blanket_failed',message='Cover checks failed; previous result preserved',stage='blanket',retryable=False,evidence_refs=[]))
                validate('run',run);repo.put_run(c,run);return
        elif run['operation'] == 'engineering.restore':
            restored = result['restore']
            validate('model', restored, 'EngineeringRevision')
            require(restored['model_ref']['project_id'] == p['id'])
            require(c.execute('SELECT 1 FROM models WHERE id=? AND project=?', (restored['model_ref']['model_id'], p['id'])).fetchone() is not None)
            revision = repo.make_revision(c, p['id'], run['module'], run['input_revision'], restored['model_ref'], restored, payload['restored_id'])
        elif run['operation'] == 'drawing.export':
            # Export starts current and must still be current at publication.
            require(current, 409, 'stale_export', 'Revision changed during conversion')
            evidence = json.loads((output/'conversion.json').read_text())
            require(evidence['draft'] is True and evidence['revision_id'] == revision['id'])
            if (output/'paint-drawings.zip').exists():
                manifest=json.loads((output/'paint-drawing-manifest.json').read_text())
                require(manifest['revision_id']==revision['id'] and manifest['model_ref']==revision['model_ref'])
                successful=[g for g in manifest['groups'] if g['status']=='succeeded']
                require(successful and manifest['summary']['succeeded']==len(successful))
                with zipfile.ZipFile(output/'paint-drawings.zip') as archive:
                    expected={'manifest.json',*[g['dwg']['path'] for g in successful]}
                    require(set(archive.namelist())==expected and len(archive.namelist())==len(expected))
                    require(json.loads(archive.read('manifest.json'))==manifest)
                    for group in successful:
                        data=archive.read(group['dwg']['path'])
                        require(data[:6]==b'AC1032' and len(data)==group['dwg']['bytes'])
            else:
                require((output/'drawing.dwg').read_bytes()[:6] == b'AC1032')
        else:
            validate('model', json.loads((output / 'engineering.json').read_text()), 'EngineeringBundle')
        if run['operation']=='engineering.rebind' and transfer['status']!='valid':
            require(set(f['path'] for f in files)=={'rebind-analysis.json'},422,'invalid_rebind_output')
        if (output/'blanket-result.json').exists():
            value=json.loads((output/'blanket-result.json').read_text())
            validate('blanket',value,'BlanketResult')
            require(run['module']=='blanket' and value['revision_id']==revision['id'] and value['model_ref']==revision['model_ref'] and value['parameters']==revision['parameters'])
            require(usable(value) or run['operation']=='blanket.generate' and reviewable_limit_preview(value))
            references=[value['native_shape_ref'],value['evaluation_shape_ref'],value['display_ref'],value['baseline']['closed_shape_ref']]
            references += [p['surface_ref'] for p in value['panels']]+[p['shape_ref'] for p in value['closures']]
            require(all(controlled(output,path).is_file() for path in references))
            require(controlled(output,value['display_ref']).read_bytes()[:4]==b'glTF')
        if (output/'blanket-net.json').exists():
            net=json.loads((output/'blanket-net.json').read_text());validate('blanket',net,'NetResult')
            require(net['revision_id']==revision['id'] and net['model_ref']==revision['model_ref'])
            require(json.loads((output/'drawing.json').read_text())==net['drawing_document'])
            if not usable(net) and not (run['operation']=='blanket.generate'
                                       and reviewable_feature_net_preview(net,blanket)):
                run.update(state='failed',artifacts=[],checks=net['checks'],tool_versions=result['tool_versions'],error=dict(code='net_failed',message='Net diagnostics require explicit adjustment; previous result preserved',stage='blanket_net',retryable=False,evidence_refs=[]))
                validate('run',run);repo.put_run(c,run);return
        if run['operation'] == 'drawing.export' and (output/'drawing-preview.png').exists():
            preview = json.loads((output/'drawing-preview.preview.json').read_text())
            require(preview.get('ok') is True and preview.get('revision_id') == revision['id'],
                    message='Preview revision mismatch')
            require(preview['input']['sha256'] == sha(output/'drawing.dwg'),
                    message='Preview DWG hash mismatch')
            require(preview['preview']['sha256'] == sha(output/'drawing-preview.png')
                    and (output/'drawing-preview.png').read_bytes()[:8] == b'\x89PNG\r\n\x1a\n',
                    message='Invalid bound preview PNG')
        final = repo.root / 'published' / run_id
        final.parent.mkdir(exist_ok=True)
        require(not final.exists(), 409)
        os.replace(output, final)
        sync_dir(final.parent)
        artifacts = []
        for f in files:
            ext = f['path'].rsplit('.', 1)[-1].upper()
            role = 'engineering_bundle' if f['path'] == 'engineering.json' else 'model' if run['operation'] == 'model.import' else 'restored_revision'
            if f['path'] in ('paint-result.json', 'drawing.json'):
                role = 'paint_result' if f['path'] == 'paint-result.json' else 'drawing_document'
            if f['path']=='paint-recommendations.json':
                role='paint_recommendations'
            if f['path']=='paint-batch-result.json':
                role='paint_batch_result'
            if f['path']=='rebind-analysis.json':
                role='revision_rebinding'
            if f['path']=='complex-analysis.json':
                role='complex_analysis'
            if f['path']=='installation-detection.json':
                role='installation_detection'
            if f['path']=='blanket-net.json':
                role='blanket_net'
            if f['path']=='blanket-result.json':
                role='blanket_result'
            elif (final/'blanket-result.json').exists():
                if ext in ('BREP','GLB'):
                    role='blanket_geometry' if ext=='BREP' else 'blanket_display'
            if run['operation'] == 'drawing.export':
                role = 'paint_batch_zip' if f['path']=='paint-drawings.zip' else 'paint_batch_manifest' if f['path']=='paint-drawing-manifest.json' else 'drawing_preview' if ext == 'PNG' else 'draft_dwg' if ext == 'DWG' else 'conversion_evidence' if ext == 'JSON' else 'draft_dxf'
            a = dict(id=uid(), run_id=run_id, revision_id=revision['id'], role=role, format=ext,
                     mime_type='application/zip' if ext == 'ZIP' else 'image/png' if ext == 'PNG' else 'model/gltf-binary' if ext == 'GLB' else 'application/json' if ext == 'JSON' else 'application/octet-stream',
                     sha256=f['sha256'], bytes=f['bytes'], relative_storage_path=f'published/{run_id}/{f["path"]}', validation=[])
            a['download_url'] = '/api/v1/artifacts/' + a['id']
            if run['operation'] == 'drawing.export':
                a['validation'] = [dict(id='draft-only',status='needs_review',scope_refs=[],observed={'draft':True},limit=None,units=None,algorithm_version='b09-draft-v1',evidence_refs=[],reason='AutoCAD and engineering human review not completed')]
                if ext == 'PNG':
                    a['validation'].append(dict(id='dwg-preview-binding', status='pass', scope_refs=[],
                        observed={'source_dwg_sha256': preview['input']['sha256'], 'revision_id': revision['id']},
                        limit=None, units=None, algorithm_version='opencadstudio-preview-v1',
                        evidence_refs=[], reason='Real application preview of this run DWG'))

            validate('common', a, 'Artifact')
            c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?)', (a['id'], p['id'], run['module'], int(role == 'model'), canonical(a)))
            artifacts.append(a)
        if run['operation'] == 'model.import':
            model = dict(snapshot=snapshot, artifacts=artifacts)
            c.execute('INSERT INTO models VALUES(?,?,?)', (snapshot['model_ref']['model_id'], p['id'], canonical(model)))
        if current and run['operation'] not in ('geometry.analyze','paint.recommend','blanket.detect_installation'):
            if 'target_revision' in payload or run['operation'] not in ('engineering.save', 'paint.generate', 'paint.generate_batch', 'blanket.generate', 'drawing.export'):
                repo.move_head(c, p, run['module'], revision)
            c.execute('INSERT OR REPLACE INTO results VALUES(?,?,?,?)', (p['id'], run['module'], revision['id'], run_id))
        run.update(state='succeeded', progress=1, artifacts=artifacts, tool_versions=result['tool_versions'])
        run['checks'] = [dict(id='publication', status='pass', scope_refs=[], observed={'current': current, **({'preview_only': True} if run['operation']=='blanket.generate' and reviewable_limit_preview(blanket) else {})},
                              limit=None, units=None, algorithm_version='b06-publication-v1', evidence_refs=[],
                              reason='Current result' if current else 'Historical result; current revision was not replaced')]
        if run['module']=='paint' and run['operation'] in ('paint.generate', 'paint.edit_regions', 'drawing.edit_annotation'):
            run['checks'] += paint['checks']
        if run['module']=='paint' and run['operation']=='paint.generate_batch':
            run['checks'] += batch['checks']
        if run['module']=='paint' and run['operation']=='paint.recommend':
            run['checks'].append(dict(id='paint_recommendations',status='pass',scope_refs=[],observed={'groups':len(recommendations['groups']),'status':recommendations['status']},limit=None,units=None,algorithm_version='paint-recommend-v1',evidence_refs=[],reason='Planar target candidates are bound to the current model revision'))
        if run['module']=='blanket' and run['operation']=='blanket.detect_installation':
            run['checks'].append(dict(id='installation_detection',status='pass',scope_refs=[],observed={'status':detection['status'],'candidate_count':len(detection['candidates'])},limit={'maximum_gap_mm':detection['maximum_gap_mm']},units='mm',algorithm_version='opposed-planar-contact-v1',evidence_refs=[],reason='Native opposed planar contacts are bound to the current model revision'))
        if run['module']=='blanket' and run['operation'] in ('blanket.generate', 'blanket.edit_shape', 'blanket.unfold', 'blanket.edit_seams', 'blanket.edit_fixed_points', 'drawing.edit_annotation'):
            run['checks'] += blanket['checks']
            if (final/'blanket-net.json').exists():run['checks'] += net['checks']
        validate('run', run)
        repo.put_run(c, run)
