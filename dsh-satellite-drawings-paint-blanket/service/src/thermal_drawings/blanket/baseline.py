"""Content-bound immutable denominator, independent of allowance and openings."""
import copy
import cadquery as cq
from ..domain.validation import fingerprint
from .selection import BlanketError

ALGORITHM='b10-installation-box-v1'


def create(parameters, selected, revision, previous=None):
    identity=dict(model_ref=parameters['model_ref'],target_instances=parameters['target_instances'],
                  installation_frame=parameters['installation_frame'],envelope_policy=parameters['envelope_policy'],
                  rule_version=parameters['rule_version'],source_hashes=selected['source_hashes'])
    identifier='baseline-'+fingerprint(identity)
    dims=selected['dimensions'];lo=selected['low'];hi=selected['high']
    data=dict(identity=identity,dimensions_mm=dims,bottom_center_mm=[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,0])
    result=dict(id=identifier,source_revision=revision,algorithm=ALGORITHM,parameters=data,
                closed_shape_ref='baseline.brep',volume_mm3=box(data).Volume(),openings_closure=[],confirmed_revision=revision)
    if previous and previous['id']==identifier:
        # Never trust a persisted denominator without reconstructing it from the
        # original source and frame. Earlier revision metadata stays immutable.
        expected=copy.deepcopy(result)
        expected['source_revision']=previous['source_revision']
        expected['confirmed_revision']=previous['confirmed_revision']
        if expected!=previous:
            raise BlanketError('baseline_integrity: immutable denominator changed')
        return copy.deepcopy(previous)
    return result


def box(data):
    x,y,z=data['dimensions_mm'];cx,cy,_=data['bottom_center_mm']
    return cq.Solid.makeBox(x,y,z,cq.Vector(cx-x/2,cy-y/2,0))
