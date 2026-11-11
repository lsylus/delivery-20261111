import copy
import json
from pathlib import Path
import cadquery as cq
from thermal_drawings.paint.selection import Model, Occurrence

ROOT=Path(__file__).resolve().parents[2]


def model_for(shape,instance='equipment',model_revision=1):
    ref=dict(project_id='project',model_id='model',model_revision=model_revision,assembly_digest='a'*64)
    refs=[dict(**ref,instance_id=instance,entity_kind='face',entity_id=f'face-{i}',signature=dict(type=f.geomType(),area_mm2=f.Area(),
          centroid_mm=list(f.Center().toTuple()),normal=list(f.normalAt().toTuple()),adjacency=[])) for i,f in enumerate(shape.Faces())]
    return Model(ref,[Occurrence(instance,shape,refs)])


def fixture(dims=(100,100,100),frame=None,shape=None):
    parameters=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text())
    if frame:
        parameters['installation_frame']=copy.deepcopy(frame)
    from thermal_drawings.blanket.selection import Frame
    source=shape if shape is not None else cq.Solid.makeBox(*dims,cq.Vector(-dims[0]/2,-dims[1]/2,0))
    source=Frame(parameters['installation_frame']).world(source)
    model=model_for(source)
    parameters['model_ref']=model.model_ref;parameters['target_instances']=['equipment']
    return parameters,model


def check(result,id_):
    return next(c for c in result['checks'] if c['id']==id_)


def opening(panel='z+',id_='port'):
    return dict(id=id_,panel=panel,loop=dict(points=[[20,20],[30,20],[30,30],[20,30]],closed=True,orientation='ccw'))
