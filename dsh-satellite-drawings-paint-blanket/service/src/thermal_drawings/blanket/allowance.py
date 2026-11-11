"""Linear XYZ allowances, always anchored at the installation bottom center."""
import math
from .selection import BlanketError
from .baseline import box


def dimensions(parameters, baseline):
    value=parameters.get('dimensions_mm')
    if value is None:
        value=[d*f for d,f in zip(baseline['parameters']['dimensions_mm'],parameters['allowance']['factors'])]
    if len(value)!=3 or any(isinstance(v,bool) or not math.isfinite(v) or v<=1e-6 for v in value):
        raise BlanketError('invalid_dimensions')
    return list(value)


def envelope(baseline, dims):
    return box(dict(dimensions_mm=dims,bottom_center_mm=baseline['parameters']['bottom_center_mm']))
