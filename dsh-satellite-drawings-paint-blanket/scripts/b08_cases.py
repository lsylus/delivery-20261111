"""Analytical CAD fixtures, independently dimensioned for B08."""
from pathlib import Path
import cadquery as cq
from geometry_core.tessellation import face_refs
from thermal_drawings.paint.selection import Model, Occurrence

REF = dict(project_id='b08-project', model_id='b08-model', model_revision=1, assembly_digest='a'*64)


def box(x, y, z, dx, dy, dz):
    return cq.Solid.makeBox(dx,dy,dz,cq.Vector(x,y,z))


def assembly(gap=0.099, *, features=False, second_x=40, transform=None):
    plate = box(0,0,-5,100,80,5)
    if features:
        plate = plate.cut(cq.Solid.makeCylinder(4,5,cq.Vector(80,60,-5)))
        plate = plate.fuse(cq.Solid.makeCylinder(4,6,cq.Vector(65,20,0)),box(20,50,0,25,2,6)).clean()
    shapes = [plate,box(10,10,gap,10,10,8),box(second_x,10,gap,10,10,8)]
    if transform:
        shapes = [transform(s) for s in shapes]
    return from_shapes(shapes)


def from_shapes(shapes):
    occurrences = []
    for i,s in enumerate(shapes):
        _,refs=face_refs(s, REF, f'occ-{i}')
        occurrences.append(Occurrence(f'occ-{i}',s,refs))
    return Model(REF, occurrences)


def target(model):
    # Largest planar face on the first occurrence facing the mounting side.
    values=[v for v in model.faces if v[0] is model.occurrences[0] and v[1].geomType()=='PLANE']
    return max(values,key=lambda v: (v[1].normalAt().z > .9, v[1].Area()))[2]


def params(model, target_ref=None):
    return dict(schema_version=1, model_ref=model.model_ref, target_face_refs=[target_ref or target(model)],scope_boundary=None,
        contact_threshold_mm=.1,contact_comparison='lt',contact_offset_mm=3,hole_offset_mm=3,
        boss_rule='protect',boss_additional_offset_mm=0,rib_rule='retain_paint',overrides=[],rule_version='paint-v1')


def override(ref, kind):
    return dict(id='classify-'+ref['instance_id']+'-'+ref['entity_id'], version=1, model_revision=ref['model_revision'],
                face_ref=ref,classification=kind,reason='Analytical fixture engineering classification')


def classify_rib(model, p):
    ref=next(r for o,f,r in model.faces if o is model.occurrences[0] and f.geomType()=='PLANE'
             and f.normalAt().z>.9 and abs(f.Area()-50)<1e-6 and abs(f.Center().z-6)<1e-6)
    p['overrides'].append(override(ref,'rib'))
    return ref


def export_fixture(destination):
    model=assembly(features=True)
    a=cq.Assembly(name='paint-analytic')
    for occ in model.occurrences:
        a.add(occ.shape,name=occ.id)
    a.export(str(destination),'STEP')


if __name__=='__main__':
    p=Path(__file__).resolve().parents[1]/'fixtures/synthetic/paint/assembly.step'
    p.parent.mkdir(parents=True,exist_ok=True)
    export_fixture(p)
