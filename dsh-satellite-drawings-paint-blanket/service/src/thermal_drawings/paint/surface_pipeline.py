"""Current curved PaintResult from native trim, boss caps and contact footprints."""
import copy,math
import cadquery as cq
from shapely.geometry import Polygon
from shapely.ops import unary_union
from ..blanket.surface_charts import trim,flat,world,distortion,descriptor
from ..blanket.surface_cover import FRAME
from ..domain.validation import fingerprint,validate
from .selection import loops,polygons,PaintError,Budget
from .checks import check
from .contacts import threshold_interval
from .curved_native import support,project,parallel_gap,common,chart

def boundary_id(wire):
    return 'boundary-'+fingerprint(sorted((e.geomType(),round(e.Length(),7),*[round(x,7) for x in e.Center().toTuple()]) for e in wire.Edges()))[:20]

def generate(params,model,revision,budget=None,output=None):
    budget=budget or Budget()
    if model.model_ref!=params['model_ref'] or len(params['target_face_refs'])!=1:raise PaintError('needs_reselection','Native charts require one exact current source face')
    occurrence,face,ref=model.resolve(params['target_face_refs'][0]);mapping,uv_domain,evidence=trim(face)
    native_loops=[list(uv_domain.exterior.coords)[:-1],*[list(h.coords)[:-1] for h in uv_domain.interiors]]
    material=Polygon([flat(mapping,p) for p in native_loops[0]],[[flat(mapping,p) for p in h] for h in native_loops[1:]]).simplify(1e-8,preserve_topology=True)
    if params['scope_boundary']:material=material.intersection(Polygon(params['scope_boundary']['points']))
    if material.is_empty or not material.is_valid:raise PaintError('invalid_scope','No valid native chart material','failed')
    checks=[];diagnostics=[];facts=[];patches=[];native=[];contacts=[];domains=[]
    def record(code,status,observed,refs=None):
        checks.append(check(code,status,refs or [ref],observed,len(checks)+1))
        if status!='pass':diagnostics.append(dict(code=code,status='needs_review' if status!='fail' else 'fail',source_refs=refs or [ref],observed=observed))
    def domain(m,geom,refs):
        value=dict(chart_id='chart-'+fingerprint(m)[:20],surface_mapping=m,material_loops=loops(geom),source_refs=refs);domains.append(value);return value
    body=domain(mapping,material,[ref]);cursor=material.bounds[2]+50
    def patch(kind,geom,d,refs,proof,origin='computed'):
        if not geom.is_empty:patches.append(dict(kind=kind,geometry=geom,domain=d,source_refs=refs,evidence=dict(proof,chart_id=d['chart_id']),origin=origin))
    ids=[boundary_id(w) for w in face.innerWires()]
    if len(set(ids))!=len(ids):raise PaintError('ambiguous_boundary_identity','Repeated native opening identity','failed')
    rules={x['boundary_id']:x for x in params.get('curved_boundary_rules',[])}
    if len(rules)!=len(params.get('curved_boundary_rules',[])) or not set(rules)<=set(ids):raise PaintError('needs_reselection','Boundary rule no longer matches exact native trim','failed')
    for i,(id_,ring,wire) in enumerate(zip(ids,native_loops[1:],face.innerWires())):
        budget.consume(pairs=1);opening=Polygon([flat(mapping,p) for p in ring]);rule=rules.get(id_)
        item=dict(boundary_id=id_,source_ref=ref,native_wire_index=i,curve_types=[e.geomType() for e in wire.Edges()],classification=rule['classification'] if rule else 'unconfirmed',reason=rule.get('reason') if rule else None)
        facts.append(item)
        if not rule:record('curved_opening_classification','needs_review',item);continue
        if rule['classification']=='hole':
            patch('hole',opening.buffer(params['hole_offset_mm'],quad_segs=64).intersection(material),body,[ref],dict(boundary_rules=[rule],metric='native_isometric_chart_distance' if mapping['mapping_type']=='isometric' else 'approximate_chart_distance',offset_mm=params['hole_offset_mm']),origin='manual')
        elif rule['classification']=='boss':
            mouth=support(face,wire);candidates=[]
            for owner,cap,cap_ref in model.faces:
                if owner is not occurrence or cap_ref==ref:continue
                budget.consume(pairs=1);gap=parallel_gap(face,cap)
                if not gap or gap['normal_dot']!=1 or gap['gap_mm']<=1e-7:continue
                footprint=project(cap,face,abs(gap['gap_mm']));area=sum(f.Area() for f in footprint.Faces())
                inside=sum(f.Area() for f in common(footprint,mouth).Faces())
                if area>1e-7 and abs(area-inside)<=max(1e-6,area*1e-8):candidates.append((cap,cap_ref,gap,footprint))
            if len(candidates)!=1:
                from .radial_boss import attached_component
                attached=attached_component(face,wire,occurrence,model,budget)
                if attached:
                    faces,footprint,proof=attached
                    proof.update(boundary_id=id_,classification='boss',boundary_rules=[rule],offset_mm=params['boss_additional_offset_mm'])
                    item['native_boss']=proof;native.extend(footprint.Faces())
                    for actual,actual_ref in faces:
                        m=descriptor(actual);g=chart(actual,m);m['chart_offset_mm']=[cursor-g.bounds[0],-g.bounds[1]];g=chart(actual,m);cursor=g.bounds[2]+50
                        from OCP.BRep import BRep_Tool
                        native_tolerance=max([BRep_Tool.Tolerance_s(actual.wrapped),*[BRep_Tool.Tolerance_s(e.wrapped) for e in actual.Edges()]])
                        distances=[cq.Vertex.makeVertex(*world(m,xy)).distance(actual) for loop in loops(g) for xy in loop['points']]
                        face_proof=dict(proof,source_face_ref=actual_ref,source_edge_tolerance_mm=native_tolerance,
                                        boundary_vertex_native_distance_max_mm=max(distances,default=0.),
                                        chart_metric='Exact plane/cylinder/cone analytic isometry; retained native BRep is authoritative',
                                        boundary_readback_definition='Distances of emitted boundary vertices to the source trimmed face; includes source pcurve/3D-edge inconsistency, not a certified global trim error bound or manufacturing approval')
                        d=domain(m,g,[actual_ref]);patch('boss',g,d,[ref,actual_ref],face_proof,'manual')
                    if params['boss_additional_offset_mm']:
                        patch('boss',opening.buffer(params['boss_additional_offset_mm'],quad_segs=64).intersection(material),body,[ref],dict(proof,scope='additional target-surface border'),'manual')
                    continue
                record('curved_boss_native_cap_unsupported','needs_review',dict(boundary_id=id_,candidate_caps=len(candidates),reason='Requires a unique native cap on a parallel analytic support; arbitrary boss cap geometry is not automatically classified'));continue
            cap,cap_ref,gap,footprint=candidates[0];m=descriptor(cap);g=chart(cap,m);m['chart_offset_mm']=[cursor-g.bounds[0],-g.bounds[1]];g=chart(cap,m);cursor=g.bounds[2]+50
            cap_domain=domain(m,g,[cap_ref]);proof=dict(boundary_id=id_,classification='boss',normal_gap=gap,native_mouth_area_mm2=mouth.Area(),native_projected_footprint_area_mm2=sum(f.Area() for f in footprint.Faces()),native_cap_area_mm2=cap.Area(),native_curve_types=sorted(set(e.geomType() for e in footprint.Edges())),source_cap_ref=cap_ref,method='Native normal-projected cap footprint within actual target mouth; protection is on the actual source cap',offset_mm=params['boss_additional_offset_mm'])
            item['native_boss']=proof;native.extend(footprint.Faces());patch('boss',g,cap_domain,[ref,cap_ref],proof,'manual')
            if params['boss_additional_offset_mm']:
                patch('boss',opening.buffer(params['boss_additional_offset_mm'],quad_segs=64).intersection(material),body,[ref,cap_ref],dict(proof,scope='additional target-surface border'))
        # rib/exclude retain paint, exactly as the explicit classification requests.
    for other in model.occurrences:
        if other is occurrence:continue
        budget.consume(pairs=1)
        if not occurrence.shape.Solids() or not other.shape.Solids():
            record('curved_contact_solid_required','needs_review',dict(instance=other.id));continue
        overlap=common(occurrence.shape,other.shape);volume=sum(abs(s.Volume()) for s in overlap.Solids())
        if volume>1e-9:record('penetration','fail',dict(instance=other.id,volume_mm3=volume));continue
        for owner,source,source_ref in model.faces:
            if owner is not other:continue
            budget.consume(pairs=1);gap=parallel_gap(face,source)
            if gap is None:
                if source.distance(face)<params['contact_threshold_mm']:record('curved_contact_nonparallel_unsupported','needs_review',dict(source_ref=source_ref,reason='No constant normal-gap proof for this surface pair; not a process-only blocker'))
                continue
            if gap['normal_dot']!=-1 or gap['gap_mm']<-1e-7:continue
            lower,upper=threshold_interval(params['contact_threshold_mm'])
            if gap['gap_mm']>upper:continue
            if gap['gap_mm']>=lower:record('threshold_uncertain','needs_review',gap,[ref,source_ref]);continue
            if gap['gap_mm']<0:record('signed_gap_uncertain','needs_review',gap,[ref,source_ref]);continue
            projected=project(source,face,abs(gap['gap_mm']));footprint=common(projected,face)
            if not footprint.Faces():continue
            geom=chart(footprint,mapping).intersection(material)
            if geom.is_empty:continue
            proof=dict(source_refs=[ref,source_ref],normal_gap=gap,native_footprint_area_mm2=sum(f.Area() for f in footprint.Faces()),native_curve_types=sorted(set(e.geomType() for e in footprint.Edges())),method='Native normal projection + target trim Common; exact constant normal gap comparison',offset_mm=params['contact_offset_mm'],metric='native_isometric_chart_distance' if mapping['mapping_type']=='isometric' else 'approximate_chart_distance')
            contacts.append(proof);native.extend(footprint.Faces());patch('contact',geom.buffer(params['contact_offset_mm'],quad_segs=64).intersection(material),body,[ref,source_ref],proof)
    if params['overrides']:record('curved_face_override_scope','needs_review',dict(reason='Use exact native boundary rules for curved mouths; planar override policies are not silently applied'))
    record('native_trim_complete','pass',dict(native_area_mm2=face.Area(),flat_material_area_mm2=material.area,native_inner_wires=len(ids),curve_types=sorted(set(e.geomType() for e in face.Edges()))))
    record('surface_manufacturing_approval','needs_review',dict(mapping_type=mapping['mapping_type'],numerical_chord_mm=.02,manufacturing_tolerance=None,definition='Native footprint and supported normal-gap proof are technical results. Material strain and process approval remain explicit.'))
    regions=[];entities=[];overlay=[]
    for d in domains:
        for loop in d['material_loops']:entities.append(dict(id=f'outline-{revision}-{len(entities)}',kind='polyline',layer='OUTLINE',source_refs=d['source_refs'],points=loop['points'],closed=True))
        selected=[p for p in patches if p['domain']['chart_id']==d['chart_id']]
        for p in polygons(unary_union([x['geometry'] for x in selected])):
            contributors=[x for x in selected if x['geometry'].intersection(p).area>1e-9];kinds=sorted(set(x['kind'] for x in contributors));refs=[]
            for x in contributors:
                for link in x['source_refs']:
                    if link not in refs:refs.append(link)
            ls=loops(p);id_=f'paint-region-{revision}-{len(regions)+1}';m=d['surface_mapping']
            regions.append(dict(id=id_,kind=kinds[0] if len(kinds)==1 else 'manual',source_refs=refs,local_frame=copy.deepcopy(FRAME),surface_mapping=m,loops=ls,protected=True,origin='manual' if any(x['origin']=='manual' for x in contributors) else 'computed',confidence=1.,check_refs=[c['id'] for c in checks],area_mm2=p.area,contributor_kinds=kinds,provenance=[dict(kind=x['kind'],source_refs=x['source_refs'],evidence=x['evidence']) for x in contributors]))
            entities.append(dict(id=id_,kind='hatch',layer='PROTECTION',source_refs=refs,outer_loop=ls[0],holes=ls[1:],pattern='ANSI31'))
            overlay.append(dict(region_id=id_,source_refs=refs,loops_world_mm=[[world(m,xy) for xy in loop['points']] for loop in ls]))
    links=[]
    for entity in entities:
        for link in entity['source_refs']:
            if link not in links:links.append(link)
    document=dict(schema_version=1,id='paint-drawing-'+revision,revision_id=revision,units='mm',frame=copy.deepcopy(FRAME),layers=[dict(name='OUTLINE',color=7,line_type='CONTINUOUS'),dict(name='PROTECTION',color=1,line_type='CONTINUOUS')],entities=entities,source_links=links)
    result=dict(schema_version=1,revision_id=revision,model_ref=model.model_ref,status='failed' if any(c['status']=='fail' for c in checks) else 'needs_review',candidate_editable=True,surface_mapping=mapping,regions=regions,diagnostics=diagnostics,checks=checks,drawing_document=document,overlay=overlay,evidence=[dict(native_trim=evidence,boundaries=facts,contacts=contacts,surface_domains=domains,distortion=distortion(mapping,loops(material)),native_footprint_ref='paint-native-footprints.brep' if native else None)],numerical_policy=dict(chord_mm=.02,gap_uncertainty_mm=1e-7,offset_quad_segments=64,manufacturing_tolerance=False),algorithm_version='b13-native-paint-v2')
    if output is not None and native:
        path=output/'paint-native-footprints.brep';cq.Compound.makeCompound(native).exportBrep(str(path))
        if not cq.Shape.importBrep(str(path)).isValid():raise PaintError('native_footprint_readback','Footprint BRep readback invalid','failed')
    validate('paint',result,'PaintResult');return result
