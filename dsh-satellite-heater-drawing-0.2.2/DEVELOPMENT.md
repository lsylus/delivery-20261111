# Heater Drawing Service

Rectangular-heater drawing engine with validated Excel import, controlled
editable CAD geometry and complete delivery packages. The native `dwg_pdf_v1`
profile saves DWG 2018 with OpenCADStudio and prints per-code/merged PDFs from
the reopened delivery DWG. See [native generation](docs/native-dwg-pdf.md) for
the one-step command, printing policy and runtime requirements. The 0.2.0
plugin adds a loopback service, profile/session isolation, a DSH Host adapter
and the browser workbench. See [plugin usage](plugin/README.md) and
[release verification](docs/plugin-release-20261110.md). Real DSH installation
and formal engineering approval are separate from development verification.

## Rebuild the development environment

The target host does not provide a shared `uv`. The commands below start from
a new shell with no `VIRTUAL_ENV`, keep every tool/cache inside the checkout,
and explicitly bind `uv sync` to the root `.venv`. Run them from the repository
root on the target Linux host; Node.js is also required for the ECMAScript
contract check.

```bash
mkdir -p .tools
curl -L https://github.com/astral-sh/uv/releases/download/0.13.7/uv-x86_64-unknown-linux-gnu.tar.gz -o /tmp/heater-uv.tar.gz
tar -xzf /tmp/heater-uv.tar.gz -C /tmp
cp /tmp/uv-x86_64-unknown-linux-gnu/uv .tools/uv
chmod 0755 .tools/uv
UV_PYTHON_INSTALL_DIR="$PWD/.python" UV_CACHE_DIR="$PWD/.uv-cache" .tools/uv python install 3.12
UV_PYTHON_INSTALL_DIR="$PWD/.python" UV_CACHE_DIR="$PWD/.uv-cache" .tools/uv venv .venv --python 3.12
VIRTUAL_ENV="$PWD/.venv" UV_PYTHON_INSTALL_DIR="$PWD/.python" UV_CACHE_DIR="$PWD/.uv-cache" .tools/uv sync --project service --frozen --active
.tools/uv build --wheel --project service --out-dir dist
mkdir -p .runtime-resources/schemas
cp -a schemas/. .runtime-resources/schemas/
.tools/uv venv .wheel-venv --python .venv/bin/python
UV_CACHE_DIR="$PWD/.uv-cache" .tools/uv pip install --python .wheel-venv/bin/python dist/heater_drawing_service-*.whl
HEATER_DRAWING_RESOURCE_ROOT="$PWD/.runtime-resources" .wheel-venv/bin/python -c "from heater_drawing.config import ResourceConfig; from heater_drawing.domain.models import ErrorCode; c=ResourceConfig.from_environment(); assert len(list(c.schema_dir.glob('*.json'))) == 6; assert ErrorCode.WORKER_INTERRUPTED.value == 'WORKER_INTERRUPTED'"
```

The lock file is authoritative. Do not run `uv lock` during routine restore.
The wheel is deliberately installed into a second environment and imported
with an external read-only resource root. B02 will add the real template;
the B01 resource check must not invent it.

Run B01 acceptance from the repository root. Refreshing the comparison
evidence is read-only with respect to all reference repositories:

```bash
.venv/bin/python -m pytest -q tests/contracts tests/planning
.venv/bin/python scripts/check_source_boundary.py --baseline docs/evidence/B01-fix/boundary-before.json --output docs/evidence/B01-fix/boundary-after.json
.venv/bin/python scripts/verify_batch.py B01 --report-dir docs/evidence/B01-fix
```

## Excel import contract

B03 exposes `heater_drawing.excel.parse_workbook(path, limits)` and
`validate_rows(rows, template=None)`. The CLI writes a complete report and
returns `1` when any business or workbook error is present:

```bash
.venv/bin/python scripts/check_excel.py \
  --input fixtures/case/加热器图纸.xlsx \
  --output docs/evidence/B03/case.json
```

The default resource limits are 10 MiB per file, 500 non-empty business rows,
501 populated rows per sheet, 64 populated columns, 2,000 ZIP entries,
100 MiB total decompressed bytes, a 1,000:1 per-entry compression ratio, and
256 Unicode characters per text field. Each limit has a matching CLI option
and can be supplied through `WorkbookLimits`. Formula cells, cached formula
results, macros, external relationships, merged populated cells, and unknown
columns are unsupported. Invalid source rows remain in `source_rows`; they are
never silently dropped.

Runtime resources are external, read-only deployment data. Set
`HEATER_DRAWING_RESOURCE_ROOT` to a directory containing `schemas/` and,
after B02, `templates/`. The wheel never searches another plugin repository.
