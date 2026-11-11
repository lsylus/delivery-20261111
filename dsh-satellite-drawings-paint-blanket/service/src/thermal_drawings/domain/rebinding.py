"""Conservative revision replay. Geometry similarity alone never picks an instance."""
import copy
import math

def entity_rebinding(old_refs,new_refs,instance_lineage,geometry_tolerance_mm=1e-6):
    if not math.isfinite(geometry_tolerance_mm) or not 0<geometry_tolerance_mm<=1e-3:
        raise ValueError('invalid numerical identity tolerance')
    result=[]
    for old in old_refs:
        lineage=instance_lineage.get(old['instance_id'],[])
        candidates=[]
        if len(lineage)==1:
            for new in new_refs:
                a,b=old['signature'],new['signature']
                area_a,area_b=a.get('area_mm2'),b.get('area_mm2')
                area_ok=area_a is None and area_b is None or area_a is not None and area_b is not None and abs(area_a-area_b)<=max(1e-6,abs(area_a)*1e-9)
                normal_ok=a.get('normal') is None and b.get('normal') is None or a.get('normal') is not None and b.get('normal') is not None and math.dist(a['normal'],b['normal'])<1e-8
                if (new['instance_id']==lineage[0] and old['entity_kind']==new['entity_kind'] and a['type']==b['type'] and
                    area_ok and normal_ok and math.dist(a['centroid_mm'],b['centroid_mm'])<=geometry_tolerance_mm and
                    len(a.get('adjacency',[]))==len(b.get('adjacency',[]))):
                    candidates.append(new)
        result.append(dict(old_ref=copy.deepcopy(old),new_ref=copy.deepcopy(candidates[0]) if len(candidates)==1 else None,
                           status='valid' if len(candidates)==1 else 'needs_reselection',candidate_refs=copy.deepcopy(candidates),
                           reason='unique lineage and native signature' if len(candidates)==1 else 'missing or ambiguous occurrence/entity correspondence'))
    # A many-to-one target is not unique correspondence, even if each lookup
    # separately has one candidate.
    for row in result:
        if row['new_ref'] is not None and sum(r['new_ref']==row['new_ref'] for r in result)>1:
            row['status']='needs_reselection'
    for row in result:
        if row['status']!='valid':row['new_ref']=None
    return dict(schema_version=1,algorithm_version='b13-rebinding-v1',history=copy.deepcopy(old_refs),mappings=result,
                status='valid' if all(r['status']=='valid' for r in result) else 'needs_reselection')

def rebind_points(old_net,new_net,state):
    from ..blanket.fixed_points import rebind
    old={p['key']:p for p in old_net['panels']};new={p['key']:p for p in new_net['panels']}
    candidate=copy.deepcopy(state)
    rejected=[]
    for point in candidate['points']:
        key=point['panel_key'];a,b=old.get(key),new.get(key)
        # Only same source model identity and exact stable panel may replay UV.
        if not a or not b or old_net['model_ref']!=new_net['model_ref'] or a['source_refs']!=b['source_refs'] or a['frame']!=b['frame']:
            rejected.append(point['id'])
    result=rebind(new_net,candidate)
    for point in result['points']:
        if point['id'] in rejected:
            point.update(status='needs_reselection',mapping_ref='invalidated:'+new_net['revision_id'],
                         diagnostic=dict(code='revision_mapping_not_unique',refs=[point['id']],location=point['uv_mm'],candidates=[]))
    return dict(state=result,history=copy.deepcopy(state),old_revision=old_net['revision_id'],new_revision=new_net['revision_id'])
