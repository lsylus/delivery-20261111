import copy
import json
from pathlib import Path
import sys
import pytest
from jsonschema import Draft202012Validator, ValidationError
from openapi_spec_validator import validate as validate_openapi

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from contracts import validate, validator, digest_files

def fixture(name):return json.loads((ROOT/f'fixtures/contracts/{name}.json').read_text())
def document(name):return json.loads((ROOT/f'contracts/{name}.schema.json').read_text())

@pytest.mark.parametrize('path',sorted((ROOT/'contracts').glob('*.schema.json')),ids=lambda p:p.name)
def test_schema_meta_and_resolved_refs(path):
    schema=json.loads(path.read_text());Draft202012Validator.check_schema(schema)
    def walk(v):
        if isinstance(v,dict):
            if '$ref' in v:
                target=v['$ref'];file,fragment=target.split('#')
                root=json.loads((path.parent/file).read_text()) if file else schema
                for component in fragment.strip('/').split('/'):root=root[component]
            for item in v.values():walk(item)
        if isinstance(v,list):
            for item in v:walk(item)
    walk(schema)

@pytest.mark.parametrize('name',['paint','blanket','drawing','operation','run'])
def test_valid_and_closed_versioned_contract(name):
    value=fixture(name);validate(name,value)
    extra=copy.deepcopy(value);extra['legacy_template_only']=True
    with pytest.raises(ValidationError):validate(name,extra)
    value['schema_version']=2
    with pytest.raises(ValidationError):validate(name,value)

@pytest.mark.parametrize('field,value',[('contact_comparison','lte'),('contact_threshold_mm',0),('boss_additional_offset_mm',-1),('rib_rule','protect_projection'),('boss_rule','ignore'),('rule_version','legacy-template'),('hole_offset_mm',None)])
def test_reject_old_paint_and_invalid_parameters(field,value):
    data=fixture('paint');data[field]=value
    with pytest.raises(ValidationError):validate('paint',data)

def test_product_defaults_are_not_old_template():
    p=document('paint')['$defs']['PaintInput']['properties'];b=document('blanket')['$defs']
    assert [p[x]['default'] for x in ['contact_threshold_mm','contact_offset_mm','hole_offset_mm','boss_additional_offset_mm']]==[0.1,3,3,0]
    assert p['contact_comparison']=={'const':'lt'}
    assert b['Allowance']['properties']['factors']['default']==[1.05]*3
    assert b['Allowance']['properties']['mode']=={'const':'linear_xyz'}
    assert b['Seam']['properties']['width_mm']['default']==15
    policy={'minimum':1,'maximum':1.2,'min_inclusive':True,'max_inclusive':True,'denominator':'immutable_baseline','overlap_included':False}
    validate('blanket',policy,'VolumeAcceptance')
    for field,bad in [('minimum',1.01),('maximum',1.1),('min_inclusive',False),('max_inclusive',False),('denominator','expanded_shape'),('overlap_included',True)]:
        with pytest.raises(ValidationError):validate('blanket',{**policy,field:bad},'VolumeAcceptance')

@pytest.mark.parametrize('change',[{'mode':'volume'},{'factors':[1.05]},{'factors':[0,1,1]},{'anchor':'centroid'},{'percent':15}])
def test_invalid_allowance(change):
    value=fixture('blanket');value['allowance'].update(change)
    with pytest.raises(ValidationError):validate('blanket',value)

def test_seam_single_owner_fold_and_spacing():
    seam={'id':'s1','edge_a':'a','edge_b':'b','pair_orientation':'opposite','kind':'join','overlap_owner_panel':'p1','width_mm':15}
    validate('blanket',seam,'Seam')
    for bad in [dict(seam,overlap_owner_panel=['p1','p2']),dict(seam,overlap_owner_panel=None),dict(seam,width_mm=-1),dict(seam,kind='fold')]:
        with pytest.raises(ValidationError):validate('blanket',bad,'Seam')
    validate('blanket',dict(seam,kind='fold',width_mm=0,overlap_owner_panel=None),'Seam')
    validate('blanket',20,'Spacing')
    for invalid in (0,-1):
        with pytest.raises(ValidationError):validate('blanket',invalid,'Spacing')

def test_model_identity_revision_and_face_kind():
    p=fixture('paint')
    for field,bad in [('project_id','another'),('model_revision',2),('assembly_digest','b'*64),('entity_kind','edge')]:
        value=copy.deepcopy(p);value['target_face_refs'][0][field]=bad
        with pytest.raises(ValidationError):validate('paint',value)

@pytest.mark.parametrize('state',['queued','running','cancel_requested','cancelled','succeeded'])
def test_run_states(state):
    r=fixture('run');r['state']=state;validate('run',r)

def test_run_failure_and_stale_not_worker_state():
    r=fixture('run');r['state']='failed'
    with pytest.raises(ValidationError):validate('run',r)
    r['error']={'code':'algorithm_failed','message':'failure','stage':'worker','retryable':False,'evidence_refs':['log']};validate('run',r)
    r['state']='stale'
    with pytest.raises(ValidationError):validate('run',r)

def test_operation_whitelist_typed_parameters_and_module():
    op=fixture('operation')
    for change in [{'operation':'shell.exec'},{'module':'blanket'},{'expected_revision':None},{'project_id':'other'},{'parameters':{'template_only':True}}]:
        with pytest.raises(ValidationError):validate('operation',{**op,**change})
    expected={'paint.recommend','paint.generate','paint.generate_batch','paint.edit_regions','blanket.detect_installation','blanket.generate','blanket.edit_shape','blanket.unfold','blanket.edit_seams','blanket.edit_fixed_points','drawing.edit_annotation','drawing.export','engineering.save','engineering.restore','engineering.rebind','geometry.analyze','history.undo','history.redo'}
    assert set(document('operation')['$defs']['OperationEnvelope']['properties']['operation']['enum'])==expected
    detection={**op,'module':'blanket','operation':'blanket.detect_installation','parameters':dict(target_instances=['occ-1'],excluded_instances=[],maximum_gap_mm=.1)}
    validate('operation',detection)
    for parameters in [dict(target_instances=[],excluded_instances=[],maximum_gap_mm=.1),dict(target_instances=['occ-1','occ-1'],excluded_instances=[],maximum_gap_mm=.1),dict(target_instances=['occ-1'],excluded_instances=[],maximum_gap_mm=-.1),dict(target_instances=['occ-1'],excluded_instances=[],maximum_gap_mm=.100001),dict(target_instances=['occ-1'],excluded_instances=[]),dict(target_instances=['occ-1'],excluded_instances=[],maximum_gap_mm=.1,other=True)]:
        with pytest.raises(ValidationError):validate('operation',{**detection,'parameters':parameters})
    for name,parameters in [('geometry.analyze',dict(face_ref=op['selection_refs'][0],deflection_mm=.5,cuts_u=[])),('engineering.rebind',dict(source_revision_id='previous'))]:
        for module in ['paint','blanket']:
            value={**op,'module':module,'operation':name,'parameters':parameters}
            validate('operation',value)
            with pytest.raises(ValidationError):validate('operation',{**value,'parameters':{}})
            with pytest.raises(ValidationError):validate('operation',{**value,'parameters':{**parameters,'shell':'exec'}})


def test_rigid_transform_and_frame_reject_mirror_scale_nonfinite():
    matrix=[[1,0,0,10],[0,1,0,20],[0,0,1,30],[0,0,0,1]]
    tr={'layout':'row_major','action':'column_vector','matrix':matrix,'kind':'rigid'}
    validate('common',tr,'Transform')
    for value in (-1,2,float('nan')):
        bad=copy.deepcopy(tr);bad['matrix'][0][0]=value
        with pytest.raises(ValidationError):validate('common',bad,'Transform')
    p=fixture('blanket');p['installation_frame']['z_axis']=[0,0,-1]
    with pytest.raises(ValidationError):validate('blanket',p)

def test_source_digest_includes_all_dependencies_and_preserves_suffix():
    files=[{'relative_path':'assembly.asm.5','sha256':'a'*64,'bytes':100},{'relative_path':'child.prt.7','sha256':'b'*64,'bytes':200}]
    data={'schema_version':1,'asset_id':'asset','main_file':'assembly.asm.5','files':files,'assembly_digest':digest_files(files),'detected_format':'Creo_ASSEMBLY','vendor':'Creo','vendor_version':None,'units':None,'load_status':'not_opened','missing_refs':None,'conversion_evidence':None}
    validate('model',data)
    assert digest_files(files)==digest_files(list(reversed(files)))
    bad=copy.deepcopy(data);bad['files'][1]['sha256']='c'*64
    with pytest.raises(ValidationError):validate('model',bad)
    for path in ('../escape','/absolute','C:\\outside','a/../b','a\\b'):
        bad=copy.deepcopy(data);bad['files'][1]['relative_path']=path;bad['assembly_digest']=digest_files(bad['files'])
        with pytest.raises(ValidationError):validate('model',bad)

def test_drawing_holes_and_entity_shapes():
    drawing=fixture('drawing');loop={'points':[[0,0],[100,0],[100,100],[0,100]],'closed':True,'orientation':'ccw'}
    hole={'points':[[10,10],[10,20],[20,20],[20,10]],'closed':True,'orientation':'cw'}
    base={'id':'entity1','layer':'OUTLINE','source_refs':[]}
    entities=[{'kind':'line','start':[0,0],'end':[10,0]},{'kind':'arc','center':[0,0],'radius_mm':5,'start_angle_rad':0,'end_angle_rad':1,'direction':'ccw'},{'kind':'circle','center':[0,0],'radius_mm':5},{'kind':'polyline','points':[[0,0],[10,10]],'closed':False},{'kind':'hatch','outer_loop':loop,'holes':[hole],'pattern':'SOLID'},{'kind':'text','position':[0,0],'text':'中文阴影','height_mm':3},{'kind':'dimension','start':[0,0],'end':[100,0],'position':[50,10],'text_override':None},{'kind':'point','position':[20,20]}]
    for entity in entities:
        drawing['entities']=[{**base,**entity}];validate('drawing',drawing)
        broken=copy.deepcopy(drawing);del broken['entities'][0][next(k for k in entity if k!='kind')]
        with pytest.raises(ValidationError):validate('drawing',broken)
    drawing['units']='inch'
    with pytest.raises(ValidationError):validate('drawing',drawing)

def test_check_not_applicable_has_reason():
    check={'id':'c','status':'not_applicable','scope_refs':[],'observed':None,'limit':None,'units':None,'algorithm_version':'v1','evidence_refs':[],'reason':None}
    with pytest.raises(ValidationError):validate('common',check,'Check')
    check['reason']='No openings on this panel';validate('common',check,'Check')

def test_summary_cannot_claim_success_without_real_counts_commands_artifacts():
    s={'schema_version':1,'batch_id':'B01','status':'passed','code_revision':'a'*40,'dirty':False,'prerequisites':[],'commands':[{'argv':['python','-m','pytest'],'exit_code':0,'log_ref':'tests.log'}],'tests':{'required':2,'passed':2,'failed':0,'skipped_required':0},'inputs':[],'artifacts':[{'path':'result.json','sha256':'a'*64}],'checks':[{'id':'check','status':'pass','reason':'actual result'}],'manual_evidence':[],'limitations':[],'resources_created':[],'resources_cleaned':[]}
    validate('summary',s)
    for key,bad in [('commands',[]),('artifacts',[]),('checks',[]),('tests',{'required':3,'passed':2,'failed':0,'skipped_required':0}),('tests',{'required':2,'passed':1,'failed':0,'skipped_required':1})]:
        with pytest.raises(ValidationError):validate('summary',{**s,key:bad})
    blocked={**s,'status':'blocked','tests':{'required':0,'passed':0,'failed':0,'skipped_required':0},'commands':[],'artifacts':[],'checks':[]};validate('summary',blocked)

def test_project_review_capability_and_selection():
    project={'id':'p1','owner_id':'owner1','name':'Example','module_states':{'paint':None,'blanket':None},'created_at':'2026-11-06T10:00:00+08:00'}
    validate('model',project,'Project')
    with pytest.raises(ValidationError):validate('model',{**project,'created_at':'not a date'},'Project')
    review={'reviewer':'person','revision_id':'r1','result_id':'result1','decision':'needs_review','reason':'Pending actual manufacturing review','at':'2026-11-06T10:00:00+08:00'}
    validate('common',review,'Review')
    with pytest.raises(ValidationError):validate('common',{**review,'decision':'succeeded'},'Review')
    capability={'vendor':'Creo','version_range':None,'os':'linux-x86_64','tool':None,'availability':'unverified','license_state':'unverified','case_ids':[]}
    validate('common',capability,'Capability')
    with pytest.raises(ValidationError):validate('common',{**capability,'availability':'assumed'},'Capability')
    mr=fixture('paint')['model_ref'];transform={'layout':'row_major','action':'column_vector','matrix':[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],'kind':'rigid'}
    selection={'schema_version':1,'session_id':'s1','module':'paint','project_id':'p1','model_ref':mr,'engineering_revision':'r1','result_id':None,'entity_refs':fixture('paint')['target_face_refs'],'view':'3d','local_coordinates':None,'annotation':None,'view_transform':transform}
    validate('operation',selection,'SelectionContext')
    with pytest.raises(ValidationError):validate('operation',{**selection,'project_id':'p2'},'SelectionContext')

def test_model_snapshot_duplicate_occurrences_and_missing_parent():
    files=[{'relative_path':'part.step','sha256':'a'*64,'bytes':100}]
    source={'schema_version':1,'asset_id':'asset','main_file':'part.step','files':files,'assembly_digest':digest_files(files),'detected_format':'STEP','vendor':None,'vendor_version':None,'units':'mm','load_status':'not_opened','missing_refs':None,'conversion_evidence':None}
    transform={'layout':'row_major','action':'column_vector','matrix':[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],'kind':'rigid'}
    instance={'instance_id':'i1','definition_id':'d1','parent_instance_id':None,'name':'First','local_transform':transform,'world_transform':transform}
    second=copy.deepcopy(instance);second.update(instance_id='i2',name='Repeated');second['world_transform']['matrix'][0][3]=10;second['local_transform']['matrix'][0][3]=10
    value={'schema_version':1,'model_ref':{**fixture('paint')['model_ref'],'assembly_digest':digest_files(files)},'units':'mm','source_manifest':source,'definitions':[{'id':'d1','shape_asset':'shape'}],'instances':[instance,second],'mesh_map_asset':None}
    validate('model',value,'ModelSnapshot')
    for key,bad in [('instance_id','i1'),('definition_id','missing'),('parent_instance_id','missing'),('parent_instance_id','i2')]:
        changed=copy.deepcopy(value);changed['instances'][1][key]=bad
        with pytest.raises(ValidationError):validate('model',changed,'ModelSnapshot')

def test_config_examples():
    for file,definition in [('converters','Converters'),('acceptance','Acceptance'),('release','Release'),('host-test','HostTest')]:
        data=json.loads((ROOT/f'work/config/{file}.example.json').read_text());validate('config',data,definition)
        data['secret_token']='must not be stored'
        with pytest.raises(ValidationError):validate('config',data,definition)

def test_case_inventory_and_unknowns():
    data=json.loads((ROOT/'fixtures/manifests/cases.json').read_text());validate('cases',data)
    assert len({c['id'] for c in data['cases']})==len(data['cases'])
    assert {c['split'] for c in data['cases']}=={'development','holdout'}
    for c in data['cases']:
        assert c['completeness']=='not_opened'
        inventory=json.loads((ROOT/c['source_manifest']).read_text())
        assert inventory['files']
        assert all(f.get('sha256') for f in inventory['files'] if f.get('detected_format') in ('STEP','DWG','Creo_PART','Creo_ASSEMBLY'))
    bad=copy.deepcopy(data);bad['cases'][0]['expected_instances']=0
    with pytest.raises(ValidationError):validate('cases',bad)
    bad=copy.deepcopy(data);bad['cases'][0]['unknown_reasons']={}
    with pytest.raises(ValidationError):validate('cases',bad)

def test_synthetic_specification_is_not_cad_result():
    data=json.loads((ROOT/'fixtures/synthetic/specifications.json').read_text())
    assert data['stage']=='specification_only_not_generated_CAD'
    box=next(c for c in data['cases'] if c['id']=='box-100')
    assert box['expected_initial_mm']==[105]*3
    assert box['expected_ratio']==105**3/100**3
    panel=next(c for c in data['cases'] if c['id']=='panel-opening')
    assert panel['expected_area_mm2']==100*80-20*20

def test_openapi_design_resolves_and_conflict_errors():
    path=ROOT/'contracts/openapi.yaml';api=json.loads(path.read_text())
    validate_openapi(api,base_uri=path.as_uri())
    assert api['servers']==[{'url':'/api/v1'}]
    for path,methods in api['paths'].items():
        for method,op in methods.items():
            assert {'401','403','404','409','422','503'}<=op['responses'].keys()
    assert api['paths']['/projects/{id}/operations']['post']['responses']['202']
