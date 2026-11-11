"""B02 is the sole STEP reader. Import this module only inside a CAD worker."""
import logging
from geometry_core import load_model_snapshot
from ..storage.assets import controlled, sha, check_step
from ..domain.errors import require


def import_step(root, run, payload, output):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    asset = payload['asset']
    source = controlled(root, asset['storage'])
    require(source.is_file() and sha(source) == asset['sha256'], message='Source asset integrity failed')
    check_step(source)
    return load_model_snapshot(source, project_id=run['project_id'], model_id=payload['model_id'],
                               model_revision=1, asset_id=asset['id'], output_dir=output)
