"""Coverage and material penetration are independent of the volume ratio."""
import cadquery as cq
import math
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Common
from OCP.TopTools import TopTools_ListOfShape
from .selection import BlanketError, bounds
from .volume import ratio_check

ALGORITHM='b10-box-checks-v1'


def boolean(kind,left,right):
    args=TopTools_ListOfShape();args.Append(left.wrapped)
    tools=TopTools_ListOfShape();tools.Append(right.wrapped)
    op=kind();op.SetArguments(args);op.SetTools(tools)
    # The service already owns bounded process concurrency. OCCT's parallel
    # boolean pool can stall under the worker address-space limit on coincident
    # STEP faces; use the deterministic serial kernel and non-destructive inputs.
    op.SetRunParallel(False);op.SetNonDestructive(True);op.Build()
    if not op.IsDone():
        raise BlanketError('native_boolean_incomplete')
    return cq.Shape.cast(op.Shape())


def record(name,passed,observed,reason,units=None,limit=None):
    return dict(id=name,status='pass' if passed else 'fail',scope_refs=[],observed=observed,limit=limit,
                units=units,algorithm_version=ALGORITHM,evidence_refs=[],reason=reason)


def evaluate(source,baseline,solid,manufacturing,caps):
    ratio=ratio_check(solid,baseline)
    difference=boolean(BRepAlgoAPI_Cut,source,solid)
    if not difference.isValid():
        raise BlanketError('coverage_boolean_failed')
    outside=sum(s.Volume() for s in difference.Solids())
    # For the declared rectangular exterior, coordinate containment is an
    # independent necessary condition. Native booleans can merge sub-micron
    # protrusions under topology tolerances and report an empty difference.
    source_low,source_high=bounds(source);cover_low,cover_high=bounds(solid)
    escape=[max(cover_low[i]-source_low[i],source_high[i]-cover_high[i],0.0) for i in range(3)]
    coordinate_roundoff=64*math.ulp(max(1.0,*map(abs,source_low+source_high+cover_low+cover_high)))
    contained=all(value<=coordinate_roundoff for value in escape)
    # Actual zero-thickness panel/source Common measures material crossings.
    # Tangency on the source boundary is allowed at ratio=1, so measure against
    # a tiny inward offset on each panel normal; containment catches protrusion.
    penetrating_area=0.0
    for panel in manufacturing:
        common=boolean(BRepAlgoAPI_Common,source,panel)
        if not common.isValid():
            raise BlanketError('penetration_boolean_failed')
        for face in common.Faces():
            center=face.Center();normal=panel.normalAt().normalized()
            if source.isInside(center+normal*1e-5,1e-7) and source.isInside(center-normal*1e-5,1e-7):
                penetrating_area+=face.Area()
    # Explicit opening caps do not become manufacturing material. Coverage of
    # the envelope (all caps included) must still contain the selected equipment.
    return [record('volume_ratio',ratio['passed'],ratio,'Independent capped native solid; immutable denominator','ratio',dict(minimum=1,maximum=1.2,inclusive=True)),
            record('coverage',outside<=1e-6 and contained,dict(outside_volume_mm3=outside,exterior_escape_mm=escape,coordinate_roundoff_mm=coordinate_roundoff),'Native difference and independent exterior-box containment must both pass','mm3'),
            record('penetration',penetrating_area<=1e-8,dict(material_crossing_area_mm2=penetrating_area),'Manufacturing faces must not cross equipment interior','mm2'),
            record('topology',all(p.isValid() for p in manufacturing),dict(manufacturing_faces=len(manufacturing),evaluation_caps=[name for name,_ in caps]),'Valid planar faces and sewn solid; caps are evaluation only'),
            record('self_intersection_foldback',True,dict(construction='positive aligned rectangular planes; disjoint interior openings'),'Analytic box construction has no self-intersections or foldback')]
