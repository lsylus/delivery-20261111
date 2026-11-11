import json
from pathlib import Path
import cadquery as cq
import pytest
from geometry_core.snapshot import load_model_snapshot
from thermal_drawings.paint.assets import load_model
from thermal_drawings.storage.assets import sha

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def assembly_model(tmp_path):
    output=tmp_path/'models/assembly'
    snapshot=load_model_snapshot(ROOT/'fixtures/synthetic/assembly-tree.step',project_id='p',model_id='m',model_revision=1,asset_id='source',output_dir=output)
    model=dict(snapshot=snapshot,artifacts=[dict(relative_storage_path=str(p.relative_to(tmp_path)),bytes=p.stat().st_size,sha256=sha(p)) for p in output.rglob('*') if p.is_file()])
    return tmp_path,model


def refresh_artifact(root,model,relative):
    entry=next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('/'+relative))
    path=root/entry['relative_storage_path'];entry.update(bytes=path.stat().st_size,sha256=sha(path))


def test_only_mapped_leaf_definitions_are_loaded_once_with_native_placement(assembly_model,monkeypatch):
    root,model=assembly_model;snapshot=model['snapshot']
    mapping=json.loads((root/'models/assembly/mesh-map.json').read_text())
    mapped={entry['face_ref']['instance_id'] for entry in mapping['faces']}
    expected=[instance for instance in snapshot['instances'] if instance['instance_id'] in mapped]
    definitions={d['id']:d['shape_asset'] for d in snapshot['definitions']}
    needed={definitions[i['definition_id']] for i in expected}
    assert len(needed)<len(definitions) and len(needed)<len(expected)
    imported=[];original=cq.Shape.importBrep
    def tracked(path):
        relative=Path(path).relative_to(root/'models/assembly').as_posix()
        assert relative in needed,'assembly aggregates must not be imported'
        imported.append(relative);return original(path)
    monkeypatch.setattr(cq.Shape,'importBrep',tracked)
    loaded=load_model(root,model)
    assert len(imported)==len(set(imported))==len(needed)
    assert [o.id for o in loaded.occurrences]==[i['instance_id'] for i in expected]
    # Model's normal validation checks each world-space native face against its
    # exact current FaceRef signature; retain independent analytic placement.
    feet=[o for o in loaded.occurrences if len(o.refs)==6]
    assert len(feet)==2
    assert [o.shape.Volume() for o in feet]==pytest.approx([6000,6000],rel=1e-6)
    assert feet[0].shape.Center().toTuple()==pytest.approx((90,60,25),abs=1e-6)
    assert feet[1].shape.Center().toTuple()==pytest.approx((95,65,25),abs=1e-6)


def test_unused_aggregate_artifacts_still_require_full_integrity(assembly_model,monkeypatch):
    root,model=assembly_model
    aggregate=model['snapshot']['definitions'][0]['shape_asset']
    path=root/'models/assembly'/aggregate
    raw=path.read_bytes();path.write_bytes(bytes([raw[0]^1])+raw[1:])
    monkeypatch.setattr(cq.Shape,'importBrep',lambda path:pytest.fail('integrity must fail before any native import'))
    with pytest.raises(ValueError,match='artifact integrity'):load_model(root,model)


def test_mapping_identity_is_verified_before_native_loading(assembly_model,monkeypatch):
    root,model=assembly_model;path=root/'models/assembly/mesh-map.json'
    mapping=json.loads(path.read_text());mapping['model_ref']['model_revision']+=1
    path.write_text(json.dumps(mapping));refresh_artifact(root,model,'mesh-map.json')
    monkeypatch.setattr(cq.Shape,'importBrep',lambda path:pytest.fail('identity must fail before any native import'))
    with pytest.raises(ValueError,match='Model map mismatch'):load_model(root,model)


def test_selected_instance_loads_only_its_definition_and_keeps_full_face_identity(assembly_model,monkeypatch):
    root,model=assembly_model
    selected='occ-1-1-1'
    full=load_model(root,model)
    expected=next(o for o in full.occurrences if o.id==selected)
    imports=[];original=cq.Shape.importBrep
    def tracked(path):imports.append(path);return original(path)
    monkeypatch.setattr(cq.Shape,'importBrep',tracked)
    scoped=load_model(root,model,instance_ids={selected})
    assert len(imports)==1
    assert [o.id for o in scoped.occurrences]==[selected]
    actual=scoped.occurrences[0]
    assert actual.refs==expected.refs
    assert actual.shape.Volume()==pytest.approx(expected.shape.Volume(),rel=1e-10)
    assert actual.shape.Center().toTuple()==pytest.approx(expected.shape.Center().toTuple(),abs=1e-10)
    assert scoped.resolve(actual.refs[0])[0].id==selected


def test_reference_occurrences_can_be_excluded_from_manufacturing_model(assembly_model):
    root,model=assembly_model
    mapped={entry['face_ref']['instance_id'] for entry in json.loads((root/'models/assembly/mesh-map.json').read_text())['faces']}
    reference=next(instance for instance in model['snapshot']['instances'] if instance['instance_id'] in mapped)
    reference['name']='Envelope_part'
    loaded=load_model(root,model,exclude_reference_occurrences=True)
    assert reference['instance_id'] not in {occurrence.id for occurrence in loaded.occurrences}
    assert loaded.occurrences


def test_scoped_load_does_not_validate_unrelated_face_geometry_but_checks_all_assets(assembly_model):
    from thermal_drawings.paint.selection import PaintError
    root,model=assembly_model;path=root/'models/assembly/mesh-map.json'
    mapping=json.loads(path.read_text())
    for entry in mapping['faces']:
        if entry['face_ref']['instance_id']=='occ-1-1-2':entry['face_ref']['signature']['area_mm2']+=10
    path.write_text(json.dumps(mapping));refresh_artifact(root,model,'mesh-map.json')
    assert len(load_model(root,model,instance_ids={'occ-1-1-1'}).occurrences)==1
    with pytest.raises(PaintError,match='ordering/signature changed'):load_model(root,model)
    unrelated=root/'models/assembly'/model['snapshot']['definitions'][0]['shape_asset']
    raw=unrelated.read_bytes();unrelated.write_bytes(bytes([raw[0]^1])+raw[1:])
    with pytest.raises(ValueError,match='artifact integrity'):
        load_model(root,model,instance_ids={'occ-1-1-1'})


@pytest.mark.parametrize('policy',['regular_box_v1','regular_cylinder_v1'])
def test_worker_regular_scope_includes_target_exclusions_and_explicit_installation(policy):
    from thermal_drawings.runtime.worker import _regular_model_scope
    parameters=dict(envelope_policy=policy,target_instances=['target','shared'],excluded_instances=['shared','port'],installation_face=dict(instance_id='wrong-installation'))
    assert _regular_model_scope(parameters)=={'target','shared','port','wrong-installation'}


@pytest.mark.parametrize('policy',['installation_box','native_surface_v1','faceted_clearance_v1','orthogonal_sections_v1'])
def test_worker_legacy_policies_keep_default_full_model_loading(policy):
    from thermal_drawings.runtime.worker import _regular_model_scope
    assert _regular_model_scope(dict(envelope_policy=policy,target_instances=['target'])) is None


def with_catalog(root,model):
    path=root/'models/assembly/mesh-map.json';mapping=json.loads(path.read_text())
    index=next(i for i,e in enumerate(mapping['faces']) if e['face_ref']['instance_id']=='occ-1-1-1' and e['face_ref']['entity_id']=='face-2')
    entry=mapping['faces'].pop(index)
    mapping['faces'].reverse()
    mapping['unrenderable_faces']=[dict(face_ref=entry['face_ref'],diagnostic=dict(reason='fixture_catalog_test',native_preserved=True))]
    path.write_text(json.dumps(mapping));refresh_artifact(root,model,'mesh-map.json')
    return mapping


def test_catalog_keeps_native_face_order_and_full_resolution(assembly_model):
    root,model=assembly_model;mapping=with_catalog(root,model)
    loaded=load_model(root,model,instance_ids={'occ-1-1-1'})
    refs=loaded.occurrences[0].refs
    assert [ref['entity_id'] for ref in refs]==[f'face-{i}' for i in range(1,7)]
    assert loaded.resolve(mapping['unrenderable_faces'][0]['face_ref'])[2]['entity_id']=='face-2'
    assert len(loaded.faces)==6


def test_catalog_never_relaxes_native_validity_gate(assembly_model,monkeypatch):
    from thermal_drawings.paint.selection import PaintError
    root,model=assembly_model;with_catalog(root,model)
    monkeypatch.setattr(cq.Shape,'isValid',lambda shape:False)
    with pytest.raises(PaintError,match='Invalid topology'):
        load_model(root,model,instance_ids={'occ-1-1-1'})


def test_unrenderable_catalog_contract_is_optional_and_strict(assembly_model):
    import copy
    from contracts import validate
    from jsonschema import ValidationError
    root,model=assembly_model;path=root/'models/assembly/mesh-map.json'
    validate('mesh-map',json.loads(path.read_text()))
    mapping=with_catalog(root,model);validate('mesh-map',mapping)
    for mutate in (lambda item:item.update(extra=True),lambda item:item.update(diagnostic=[]),lambda item:item.pop('face_ref')):
        invalid=copy.deepcopy(mapping);mutate(invalid['unrenderable_faces'][0])
        with pytest.raises(ValidationError):validate('mesh-map',invalid)
    foreign=copy.deepcopy(mapping);foreign['unrenderable_faces'][0]['face_ref']['model_revision']+=1
    with pytest.raises(ValidationError,match='another model revision'):validate('mesh-map',foreign)


def test_nonzero_valid_native_face_can_remain_in_display_failure_catalog(assembly_model):
    from contracts import validate
    from thermal_drawings.paint.selection import PaintError
    root,model=assembly_model;mapping=with_catalog(root,model)
    entry=mapping['unrenderable_faces'][0]
    entry['diagnostic']=dict(reason='native_mesher_failure',native_valid=True,native_preserved=True)
    assert entry['face_ref']['signature']['area_mm2']>1
    validate('mesh-map',mapping)
    path=root/'models/assembly/mesh-map.json'
    path.write_text(json.dumps(mapping));refresh_artifact(root,model,'mesh-map.json')
    loaded=load_model(root,model,instance_ids={'occ-1-1-1'})
    occurrence,face,ref=loaded.resolve(entry['face_ref'])
    assert face.isValid() and occurrence.shape.isValid()
    assert face.Area()==pytest.approx(ref['signature']['area_mm2'],rel=1e-10)
    assert [r['entity_id'] for r in occurrence.refs]==[f'face-{i}' for i in range(1,7)]
    assert all(e['face_ref']['entity_id']!='face-2' or e['face_ref']['instance_id']!='occ-1-1-1' for e in mapping['faces'])
    # Display metadata cannot authorize stale or false source signatures.
    entry['face_ref']['signature']['area_mm2']+=1
    path.write_text(json.dumps(mapping));refresh_artifact(root,model,'mesh-map.json')
    with pytest.raises(PaintError,match='ordering/signature changed'):
        load_model(root,model,instance_ids={'occ-1-1-1'})
