"""Round Euclidean offsets, material clipping and positive-overlap-only merge."""
from shapely.ops import unary_union
from .selection import polygons, AREA_EPS, PaintError

QUAD_SEGS = 2048


def protect(patches, domains, budget):
    pieces = []
    for patch in patches:
        domain = next(d['geometry'] for d in domains if d['frame'] == patch['frame'])
        for component in polygons(patch['geometry']):
            budget.consume()
            buffered = component.buffer(patch['offset'], quad_segs=QUAD_SEGS) if patch['offset'] else component
            clipped = buffered.intersection(domain)
            if not clipped.is_valid:
                raise PaintError('offset_failure', 'Offset/clip produced invalid geometry', 'failed')
            for polygon in polygons(clipped):
                budget.consume(points=len(polygon.exterior.coords)+sum(len(r.coords) for r in polygon.interiors))
                pieces.append(dict(geometry=polygon, frame=patch['frame'], contributors=[patch]))
    # Connected overlap graph; touching boundaries alone never unite two footprints.
    groups = []
    for piece in pieces:
        merged = piece
        again = True
        while again:
            again = False
            for index, group in enumerate(groups):
                budget.consume(pairs=1)
                if group['frame'] == merged['frame'] and group['geometry'].intersection(merged['geometry']).area > AREA_EPS:
                    merged = dict(geometry=unary_union([group['geometry'],merged['geometry']]), frame=merged['frame'],
                                  contributors=group['contributors']+merged['contributors'])
                    groups.pop(index)
                    again = True
                    break
        groups.append(merged)
    return groups
