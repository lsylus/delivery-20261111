"""Current editable native-surface candidates; evaluation shell is not material."""
import copy,json,math
import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common,BRepAlgoAPI_Cut
from .surface_charts import partition,world,native_uv,world_uv,distortion
from .checks import record,boolean
from .exterior import close_recesses
from .selection import BlanketError,shape_hash
from ..domain.validation import canonical,fingerprint,validate

FRAME=dict(origin=[0.,0.,0.],x_axis=[1.,0.,0.],y_axis=[0.,1.,0.],z_axis=[0.,0.,1.],units='mm',handedness='right')

def generate(parameters,model,revision,output=None,previous=None):
    validate('blanket',parameters)
    if model.model_ref!=parameters['model_ref']:raise BlanketError('needs_reselection: native surface model')
    if parameters['allowance']['factors']!=[1,1,1]:raise BlanketError('native_surface_fit_uses_unit_allowance; clearance approval remains pending')
    selected=[model.resolve(ref) for ref in parameters['included_faces']]
    if not selected or len(set(o.id for o,f,r in selected))!=1 or len(parameters['target_instances'])!=1:raise BlanketError('select_native_faces_from_one_occurrence')
    if any(o.id!=parameters['target_instances'][0] or ref in parameters['excluded_faces'] for o,f,ref in selected):raise BlanketError('conflicting_native_surface_scope')
    if parameters['openings']:raise BlanketError('native_trim_openings_come_from_source; edit_source_or_surface_cuts')
    source=selected[0][0].shape;baseline_shape,closure=close_recesses(source)
    identity=dict(model_ref=model.model_ref,instance=selected[0][0].id,source_hash=shape_hash(source),algorithm='b13-native-surface-v1',closure_policy=closure['closure_policy'])
    baseline=dict(id='baseline-'+fingerprint(identity),source_revision=revision,algorithm='b13-native-surface-v1',parameters=dict(identity=identity,closure=closure),closed_shape_ref='baseline.brep',volume_mm3=baseline_shape.Volume(),openings_closure=['evaluation-shell-only'],confirmed_revision=revision)
    baseline=json.loads(canonical(baseline))
    if previous and previous['id']==baseline['id']:
        expected=copy.deepcopy(baseline);expected.update(source_revision=previous['source_revision'],confirmed_revision=previous['confirmed_revision'])
        if expected!=previous:raise BlanketError('baseline_integrity')
        baseline=copy.deepcopy(previous)
    panels=[];native=[];coverage=[];options=parameters.get('surface_options',{});chord=options.get('chart_chord_mm',.02)
    for occ,face,ref in selected:
        u0,u1,v0,v1=face._uvBounds();cuts=options.get('cuts_u',[(u0+u1)/2])
        if options.get('partition_plan')=='cube_greatcircle_v1':
            if options.get('cuts_u'):raise BlanketError('cube_plan_uses_rotation_not_u_cuts')
            from .sphere_atlas import partition as atlas_partition
            prepared=atlas_partition(face,options.get('rotation_deg',[0,0,0]),chord)
        else:
            mapping,patches,evidence=partition(face,cuts,chord);prepared=[]
            for index,patch in enumerate(patches):
                a,b=patch['u_interval'];clipped=boolean(BRepAlgoAPI_Common,face,face.trim(a,b,v0,v1));fs=clipped.Faces()
                if len(fs)!=1:raise BlanketError('native_chart_disconnected_trim_requires_partition')
                prepared.append(dict(patch,mapping=dict(mapping,uv_bounds=[a,b,v0,v1]),actual=fs[0],evidence=evidence,identity=dict(interval=[a,b],index=index)))
        part_faces=[]
        for patch in prepared:
            actual=patch['actual'];part_faces.append(actual);local_mapping=patch['mapping'];evidence=patch['evidence']
            key='surface-'+fingerprint(dict(ref=ref,**patch['identity']))[:18]
            loops=patch['loops'];from OCP.BRepAdaptor import BRepAdaptor_Surface
            adaptor=BRepAdaptor_Surface(actual.wrapped)
            def native_point(xy):
                # Evaluate the actual retained native face, whose UV frame may
                # differ from a rotated atlas chart.
                uv=actual.paramAt(cq.Vector(*world(local_mapping,xy)));p=adaptor.Value(*uv);return [p.X(),p.Y(),p.Z()]
            samples=[dict(flat_mm=xy,world_mm=native_point(xy)) for loop in loops for xy in loop['points']]
            # Native trim records, true geometry and flattened numerical boundary coexist.
            panels.append(dict(id=revision+':'+key,key=key,surface_ref='panels/'+key+'.brep',outer_loop=loops[0],holes=loops[1:],frame=copy.deepcopy(FRAME),source_refs=[ref],mapping_ref=revision+':'+key+':surface',surface_mapping=local_mapping,surface_trim=dict(distortion=distortion(local_mapping,loops),evidence=evidence,native_area_mm2=actual.Area(),flat_area_mm2=patch['flat_area_mm2'],area_difference_mm2=patch['flat_area_mm2']-actual.Area(),native_boundary_samples=samples)))
            native.append(actual)
        # Sequential native Cut avoids OCCT treating adjacent same-domain
        # faces in a compound as overlapping Boolean tools.
        uncovered=face
        for part in part_faces:uncovered=boolean(BRepAlgoAPI_Cut,uncovered,part)
        uncovered_area=sum(f.Area() for f in uncovered.Faces())
        coverage.append(dict(uncovered_area_mm2=uncovered_area,source_ref=ref,source_area_mm2=face.Area(),native_patch_area_mm2=sum(f.Area() for f in part_faces),area_difference_mm2=sum(f.Area() for f in part_faces)-face.Area()))
    outside=sum(s.Volume() for s in boolean(BRepAlgoAPI_Cut,source,baseline_shape).Solids())
    checks=[record('volume_ratio',True,dict(baseline_volume_mm3=baseline_shape.Volume(),cover_volume_mm3=baseline_shape.Volume(),ratio=1.),'Fixed closed exterior evaluation shell; selected native surfaces are a scoped material candidate','ratio',dict(minimum=1,maximum=1.2)),
      record('coverage',outside<1e-6 and all(x['uncovered_area_mm2']<1e-7 for x in coverage),dict(outside_volume_mm3=outside,selected_surface_patches=coverage),'Native source containment and exact trimmed surface partition','mm3'),
      record('penetration',True,dict(material_crossing_area_mm2=0.,construction='Exact subset of original selected boundary faces'),'Native boundary faces are not displaced into source interior','mm2'),
      dict(record('local_clearance',True,dict(distance_mm=0.,manufacturing_tolerance=None),'Native fitted surface touches the source; no approved clearance','mm'),status='needs_review'),
      record('topology',all(f.isValid() for f in native),dict(native_faces=len(native),native_trim_retained=True),'Native trimmed BRep retained'),
      dict(record('unfolding',True,dict(state='requires_current_net'),'Matching current net not yet evaluated'),status='not_run')]
    if any(p['surface_mapping']['mapping_type']!='isometric' for p in panels):
        checks.append(dict(record('surface_distortion',True,dict(manufacturing_tolerance=None,mapping='non-isometric spherical chart',patch_measurements=[p['surface_trim']['distortion'] for p in panels]),'Editable approximate patch plan; distortion must be measured and approved'),status='needs_review'))
    for check in checks:check['algorithm_version']='b13-native-surface-v1'
    b=baseline_shape.BoundingBox()
    result=dict(schema_version=1,revision_id=revision,model_ref=copy.deepcopy(model.model_ref),parameters=copy.deepcopy(parameters),baseline=baseline,dimensions_mm=[b.xlen,b.ylen,b.zlen],panels=panels,native_shape_ref='manufacturing.brep',evaluation_shape_ref='evaluation.brep',display_ref='cover.glb',closures=[dict(id='evaluation-shell-only',shape_ref='closures/evaluation-shell.brep',evaluation_only=True)],checks=checks,status='failed' if any(c['status']=='fail' for c in checks) else 'needs_review',candidate_editable=True,algorithm_version='b13-native-surface-v1',downstream=dict(revision_id=revision,panels='candidates',unfolding='not_computed',checks_revision=revision))
    validate('blanket',result,'BlanketResult')
    if output is not None:
        output.mkdir(parents=True,exist_ok=True);(output/'panels').mkdir(exist_ok=True);(output/'closures').mkdir(exist_ok=True)
        for path in ['baseline.brep','evaluation.brep','closures/evaluation-shell.brep']:baseline_shape.exportBrep(str(output/path))
        cq.Compound.makeCompound(native).exportBrep(str(output/'manufacturing.brep'));assembly=cq.Assembly()
        for panel,face in zip(panels,native):
            face.exportBrep(str(output/panel['surface_ref']));assembly.add(face,name=panel['id'].replace(':','_'),color=cq.Color(.75,.65,.25))
        assembly.export(str(output/'cover.glb'))
        from .display import normalize
        normalize(output/'cover.glb',panels);(output/'blanket-result.json').write_text(canonical(result))
    return result
