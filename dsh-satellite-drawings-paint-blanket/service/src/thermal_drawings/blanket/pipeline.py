"""B10 worker entry; native manufacturing, evaluation and display artifacts."""
import copy
import json
import cadquery as cq
from ..domain.validation import validate, canonical
from .selection import select, BlanketError, shape_hash
from .baseline import create, box
from .allowance import dimensions, envelope
from .surfaces import build
from .volume import close
from .checks import evaluate


def generate(parameters,model,revision,output=None,previous=None):
    validate('blanket',parameters)
    if parameters['envelope_policy']=='feature_composite_v1':
        from .feature_cover import generate as feature_generate
        return feature_generate(parameters,model,revision,output,previous)
    if parameters['envelope_policy'] in ('regular_box_v1', 'regular_cylinder_v1'):
        from .regular_cover import generate as regular_generate
        return regular_generate(parameters,model,revision,output,previous)
    if parameters['envelope_policy']=='faceted_clearance_v1':
        from .faceted_cover import generate as faceted_generate
        return faceted_generate(parameters,model,revision,output,previous)
    if parameters['envelope_policy']=='native_surface_v1':
        from .surface_cover import generate as surface_generate
        return surface_generate(parameters,model,revision,output,previous)
    if parameters['envelope_policy']=='orthogonal_sections_v1':
        from .complex_envelopes import generate as complex_generate
        return complex_generate(parameters,model,revision,output,previous)
    if (parameters['envelope_policy']!='installation_box' or parameters['cut_edges'] or parameters['fold_edges']
            or parameters['overlaps'] or parameters['fixed_points'] or parameters['unfold_base_panel'] is not None):
        raise BlanketError('unsupported_B11_B13: only regular box construction is implemented')
    selected=select(parameters,model)
    baseline=create(parameters,selected,revision,previous)
    dims=dimensions(parameters,baseline)
    panels,native,caps=build(parameters,baseline,dims,selected,revision)
    evaluation=close(native,caps)
    base=box(baseline['parameters'])
    checks=evaluate(selected['shape'],base,evaluation,native,caps)
    if selected['source_hashes']!={o.id:shape_hash(o.shape) for o in model.occurrences if o.id in parameters['target_instances']}:
        raise BlanketError('source_mutated')
    result=dict(schema_version=1,revision_id=revision,model_ref=copy.deepcopy(model.model_ref),baseline=baseline,
                parameters=copy.deepcopy(parameters),dimensions_mm=dims,panels=panels,
                native_shape_ref='manufacturing.brep',evaluation_shape_ref='evaluation.brep',display_ref='cover.glb',
                closures=[dict(id=name,shape_ref=f'closures/{i}.brep',evaluation_only=True) for i,(name,_) in enumerate(caps)],
                checks=checks,status='passed' if all(c['status']=='pass' for c in checks) else 'failed',
                algorithm_version='b10-box-v1',downstream=dict(revision_id=revision,panels='candidates',unfolding='not_computed',checks_revision=revision))
    validate('blanket',result,'BlanketResult')
    if output is not None:
        output.mkdir(parents=True,exist_ok=True)
        frame=selected['frame'];world=[frame.world(s) for s in native]
        cq.Compound.makeCompound(world).exportBrep(str(output/'manufacturing.brep'))
        frame.world(evaluation).exportBrep(str(output/'evaluation.brep'))
        frame.world(base).exportBrep(str(output/'baseline.brep'))
        (output/'panels').mkdir(exist_ok=True);(output/'closures').mkdir(exist_ok=True)
        for panel,shape in zip(panels,world,strict=True):
            shape.exportBrep(str(output/panel['surface_ref']))
        for i,(_,shape) in enumerate(caps):
            frame.world(shape).exportBrep(str(output/f'closures/{i}.brep'))
        assembly=cq.Assembly()
        for panel,shape in zip(panels,world,strict=True):
            assembly.add(shape,name=panel['id'].replace(':','_'),color=cq.Color(.75,.65,.25))
        assembly.export(str(output/'cover.glb'))
        from .display import normalize
        normalize(output/'cover.glb',panels)
        (output/'blanket-result.json').write_text(canonical(result))
    return result
