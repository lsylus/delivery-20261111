"""Native B13 diagnostic jobs; measured results never authorize manufacture."""
from .validation import canonical,validate
from .errors import require

def prepare(repo,c,p,principal,request,payload):
    params=request['parameters'];ref=params['face_ref']
    require(all(ref[k]==payload['revision']['model_ref'][k] for k in payload['revision']['model_ref']),409,'needs_reselection')

def compute(model,revision,parameters,module,output=None):
    from ..blanket.developable import Developable
    from ..blanket.segmentation import piecewise
    from ..paint.curved_targets import inspect_target,feature_inventory,edge_band
    occurrence,face,ref=model.resolve(parameters['face_ref'])
    if 'installation_setup' in parameters:
        if module!='blanket' or parameters['cuts_u'] or parameters.get('envelope_offset_mm') is not None:
            raise ValueError('installation measurement cannot mix paint, surface cuts or offsets')
        from ..blanket.installation import measure
        result=measure(model,ref,parameters['installation_setup'])
        return dict(schema_version=1,revision_id=revision['id'],model_ref=model.model_ref,source_ref=ref,module=module,
                    algorithm_version='b13-analysis-v1',result=result,status='needs_review',manufacturing_approved=False)
    if module=='paint':
        if parameters['cuts_u']:raise ValueError('paint analysis does not accept U cuts')
        if parameters.get('envelope_offset_mm') is not None:raise ValueError('paint analysis does not accept envelope offsets')
        result=inspect_target(face,ref,parameters['deflection_mm'])
        result['features']=feature_inventory(occurrence.shape)
        # Evaluate actual target mouths only. Recess protection uses native
        # distance; bosses are kept as explicit process candidates without an
        # invented 3mm expansion.
        index=next(i for i,f in enumerate(occurrence.shape.Faces()) if f.isSame(face))
        bands=[]
        for feature in result['features']:
            if feature['target_face']!=index:continue
            if feature['candidate']=='recess_or_hole':
                wire=face.innerWires()[int(feature['id'].rsplit('-',1)[1])]
                band=edge_band(face,wire,3.0)
                band['feature_id']=feature['id'];bands.append(band)
        result['native_protection_candidates']=bands
    else:
        if face.geomType() in ('PLANE','CYLINDER','CONE'):
            result=Developable(face).report(parameters['cuts_u'])
        else:
            if parameters['cuts_u']:raise ValueError('piecewise cuts use triangle adjacency, not native U cuts')
            result=piecewise(face,parameters['deflection_mm'])
    if module=='blanket':
        from ..blanket.developable import drawing
        result['drawing_document']=drawing(result,ref,revision['id'])
        if output is not None and result['drawing_document'] is not None:
            (output/'surface-drawing.json').write_text(canonical(result['drawing_document']))
        if parameters.get('envelope_offset_mm') is not None:
            from ..blanket.exterior import offset_candidate
            baseline,cover,material,envelope=offset_candidate(occurrence.shape,parameters['envelope_offset_mm'])
            result['envelope_candidate']=envelope
            if output is not None:
                baseline.exportBrep(str(output/'surface-baseline.brep'))
                cover.exportBrep(str(output/'surface-evaluation.brep'))
                material.exportBrep(str(output/'surface-manufacturing.brep'))
    return dict(schema_version=1,revision_id=revision['id'],model_ref=model.model_ref,source_ref=ref,module=module,
                algorithm_version='b13-analysis-v1',result=result,status='needs_review',manufacturing_approved=False)
