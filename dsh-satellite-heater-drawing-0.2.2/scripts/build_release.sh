#!/usr/bin/env bash
set -euo pipefail
heater_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$heater_repo"
command -v uv >/dev/null
command -v node >/dev/null
command -v npm >/dev/null
if [[ ! -x .venv/bin/python ]]; then
  uv venv .venv --python 3.12 --seed
fi
export UV_PROJECT_ENVIRONMENT="$heater_repo/.venv"
uv sync --project service --frozen
mkdir -p dist/heater-wheelhouse dist/plugin-release
uv export --project service --frozen --no-dev --no-emit-project --format requirements-txt --output-file dist/heater-runtime-requirements.txt
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip download --disable-pip-version-check --require-hashes --only-binary=:all: --dest dist/heater-wheelhouse -r dist/heater-runtime-requirements.txt
.venv/bin/python scripts/prepare_plugin_runtime.py
(
  cd plugin
  npm ci
  npm run build
  npm pack --pack-destination ../dist/plugin-release
)
sha256sum dist/plugin-release/*.tgz > dist/plugin-release/SHA256SUMS.txt
