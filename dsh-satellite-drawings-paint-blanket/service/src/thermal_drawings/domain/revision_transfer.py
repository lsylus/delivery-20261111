"""Cross-source revision transfer through unique native geometry correspondence."""
from thermal_drawings.domain.acceptance import usable
import copy,math
from .rebinding import entity_rebinding
from .validation import canonical,validate
from .errors import require

def prepare(repo,c,p,principal,request,payload):
    from ..storage.repository import uid
    source=repo.revision(c,p['id'],principal.module,request['parameters']['source_revision_id'])
    require(source['id']!=payload['revision']['id'],422,'same_revision')
    # Restrict replay to this branch's actual ancestors. No foreign project or
    # alternate module state can inject editing intent.
    require(source['id'] in [r['id'] for r in payload['history']],409,'source_not_ancestor')
    payload['rebind_source']=source
    payload['rebind_model']=repo.model(c,principal,p['id'],source['model_ref']['model_id'])
    payload['rebind_id']=uid()

def compute(old_model,new_model,source,current,revision_id,module,output):
    old_refs=[r for o in old_model.occurrences for r in o.refs]
    new_refs=[r for o in new_model.occurrences for r in o.refs]
    lineage={}
    for old in old_model.occurrences:
        lineage[old.id]=[]
        for new in new_model.occurrences:
            if len(old.refs)!=len(new.refs):continue
            # Complete signatures + bijection must identify each occurrence;
            # repeated coincident instances remain ambiguous.
            trial=entity_rebinding(old.refs,new.refs,{old.id:[new.id]})
            if trial['status']=='valid':lineage[old.id].append(new.id)
    audit=entity_rebinding(old_refs,new_refs,lineage)
    audit.update(source_revision=source['id'],target_revision=current['id'],source_model_ref=old_model.model_ref,target_model_ref=new_model.model_ref,
                 history_revision=copy.deepcopy(source),full_acceptance=False)
    if audit['status']!='valid':
        (output/'rebind-analysis.json').write_text(canonical(audit));return audit
    from ..blanket.checks import boolean
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    for row in audit['mappings']:
        _,old_face,_=old_model.resolve(row['old_ref']);_,new_face,_=new_model.resolve(row['new_ref'])
        common=boolean(BRepAlgoAPI_Common,old_face,new_face)
        area=sum(f.Area() for f in common.Faces())
        if abs(area-old_face.Area())>max(1e-7,old_face.Area()*1e-9):
            audit.update(status='needs_reselection',reason='signature matched but native trimmed domains differ')
            row.update(status='needs_reselection',new_ref=None)
    if audit['status']!='valid':
        (output/'rebind-analysis.json').write_text(canonical(audit));return audit
    mappings={canonical(r['old_ref']):r['new_ref'] for r in audit['mappings']}
    def replace(value):
        if isinstance(value,dict):
            if canonical(value) in mappings:return copy.deepcopy(mappings[canonical(value)])
            if value==old_model.model_ref:return copy.deepcopy(new_model.model_ref)
            result={k:replace(v) for k,v in value.items()}
            if 'target_instances' in result:result['target_instances']=[lineage[k][0] for k in result['target_instances']]
            return result
        if isinstance(value,list):return [replace(v) for v in value]
        return value
    candidate=replace(source);candidate.update(id=revision_id,parent_id=current['id'],model_ref=new_model.model_ref)
    # Old input fingerprint is recomputed by repository.make_revision at publish.
    candidate.pop('input_fingerprint',None)
    from ..blanket.panels import NetError
    try:
        if module=='blanket' and candidate['parameters'].get('rule_version')=='blanket-v1':
            from ..blanket.pipeline import generate
            from ..blanket.net_operations import rebuild_net
            cover=generate(candidate['parameters'],new_model,revision_id)
            net=rebuild_net(cover,candidate,None) if usable(cover) else None
            if not usable(cover) or candidate['document_edits'] and (net is None or not usable(net)):
                audit.update(status='needs_reselection',reason='replayed cover/net or fixed-point domain failed')
            else:
                cover=generate(candidate['parameters'],new_model,revision_id,output)
                rebuild_net(cover,candidate,output)
        elif module=='paint' and candidate['parameters'].get('rule_version'):
            from ..paint.pipeline import generate
            from ..drawing.document_edits import apply_edits
            paint=apply_edits(generate(candidate['parameters'],new_model,revision_id),candidate)
            if not usable(paint):audit.update(status='needs_reselection',reason='replayed paint validation failed')
            else:
                (output/'paint-result.json').write_text(canonical(paint))
                (output/'drawing.json').write_text(canonical(paint['drawing_document']))
    except NetError as error:
        audit.update(status='needs_reselection',reason='replayed geometry or fixed-point domain failed: '+str(error))
    if audit['status']=='valid':audit['candidate']=candidate
    (output/'rebind-analysis.json').write_text(canonical(audit))
    return audit
