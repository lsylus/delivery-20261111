"""Parameter-consistent sphere pcurves checked against retained native 3D edges."""
import math
import numpy as np
from .panels import NetError

def attach(edges,surface,origin,radius,x_axis,z_axis):
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Curve,BRepAdaptor_Curve2d,BRepAdaptor_Surface
    from OCP.Geom2dAPI import Geom2dAPI_Interpolate
    from OCP.TColgp import TColgp_HArray1OfPnt2d
    from OCP.TColStd import TColStd_HArray1OfReal
    from OCP.gp import gp_Pnt2d
    # OCCT's generic sphere projection can leave a valid-looking pcurve nearly
    # 0.01 mm off its exact 3D circle near a pole. Interpolate with the *same*
    # native curve parameters and refine against independent 3D evaluations.
    y_axis=np.cross(z_axis,x_axis);center=np.array(origin);builder=BRep_Builder()
    for edge in edges:
        curve=BRepAdaptor_Curve(edge.wrapped);lo,hi=curve.FirstParameter(),curve.LastParameter();count=33
        while True:
            points=TColgp_HArray1OfPnt2d(1,count);parameters=TColStd_HArray1OfReal(1,count)
            for i,t in enumerate(np.linspace(lo,hi,count),1):
                v=curve.Value(float(t));q=(np.array([v.X(),v.Y(),v.Z()])-center)/radius
                uv=[math.atan2(float(np.dot(q,y_axis)),float(np.dot(q,x_axis))),math.asin(max(-1.,min(1.,float(np.dot(q,z_axis)))))]
                points.SetValue(i,gp_Pnt2d(*uv));parameters.SetValue(i,float(t))
            interpolator=Geom2dAPI_Interpolate(points,parameters,False,1e-10);interpolator.Perform()
            if not interpolator.IsDone():raise NetError('native_sphere_pcurve_interpolation_failed')
            pc=interpolator.Curve();error=0.
            for t in np.linspace(lo,hi,4*(count-1)+1):
                uv=pc.Value(float(t));error=max(error,curve.Value(float(t)).Distance(surface.Value(uv.X(),uv.Y())))
            if error<1e-7:break
            count=2*count-1
            if count>4097:raise NetError('native_sphere_pcurve_precision_budget')
        builder.UpdateEdge(edge.wrapped,pc,surface,TopLoc_Location(),1e-7)
        builder.SameRange(edge.wrapped,True);builder.SameParameter(edge.wrapped,True)
