"""Volume only on an independently sewn, valid, closed single solid."""
import math
import cadquery as cq
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
from OCP.TopoDS import TopoDS
from .selection import BlanketError


def closed_volume(shape):
    if not shape.isValid() or len(shape.Solids())!=1 or shape.ShapeType()!='Solid':
        raise BlanketError('invalid_evaluation_solid')
    if not shape.outerShell().Closed():
        raise BlanketError('open_evaluation_shell')
    value=shape.Volume()
    if not math.isfinite(value) or value<=0:
        raise BlanketError('nonpositive_evaluation_volume')
    return value


def close(manufacturing,caps):
    sewing=BRepBuilderAPI_Sewing(1e-7)
    for f in [*manufacturing,*[shape for _,shape in caps]]:
        sewing.Add(f.wrapped)
    sewing.Perform()
    shell=cq.Shape.cast(sewing.SewedShape())
    if shell.ShapeType()!='Shell' or not shell.Closed() or not shell.isValid():
        raise BlanketError('invalid_evaluation_closure')
    result=cq.Solid.makeSolid(cq.Shell(TopoDS.Shell_s(shell.wrapped)))
    closed_volume(result)
    return result


def ratio_check(cover, baseline):
    a,b=closed_volume(cover),closed_volume(baseline)
    ratio=a/b
    # Inclusive mathematical endpoints: absorb only accumulated floating ULPs,
    # never a geometric/manufacturing tolerance or a rounded decimal ratio.
    eps=32*math.ulp(max(1.0,abs(ratio)))
    return dict(ratio=ratio,cover_volume_mm3=a,baseline_volume_mm3=b,passed=1-eps<=ratio<=1.2+eps,boundary_ulp_tolerance=eps)
