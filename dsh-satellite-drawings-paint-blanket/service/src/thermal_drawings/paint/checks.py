"""C03 diagnostics retain uncertainty independently of job completion."""
VERSION = 'b08-planar-v1-r1'


def check(code, status, refs, observed, index):
    return dict(id=f'paint-check-{index}', status=status, scope_refs=refs, observed=observed, limit=None,
                units=None, algorithm_version=VERSION, evidence_refs=[], reason=code)
