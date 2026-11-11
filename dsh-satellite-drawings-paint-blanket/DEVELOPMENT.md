# Development and deployment

## 1. Clean-clone environment

Required tools:

- Linux x86_64
- Node.js `^22.19.0 || >=24`
- npm matching the lock file
- Python `3.12`
- `uv`

From the repository root:

```bash
uv sync --frozen --python 3.12
npm ci
```

Do not regenerate `uv.lock` or `package-lock.json` during a normal restore.

## 2. Validation

Run Python suites separately because several test domains intentionally have their own `conftest.py`:

```bash
.venv/bin/python -m pytest tests/blanket
.venv/bin/python -m pytest tests/paint
.venv/bin/python -m pytest tests/contracts
.venv/bin/python -m pytest tests/runtime
.venv/bin/python -m pytest tests/integration
.venv/bin/python -m pytest tests/geometry
.venv/bin/python -m pytest tests/formats
.venv/bin/python -m pytest tests/e2e
```

Run Node and TypeScript checks:

```bash
node --test \
  packages/host-bridge/tests/bridge.test.mjs \
  packages/workbench-common/tests/component-colors.test.mjs \
  packages/workbench-common/tests/providers.test.mjs \
  plugins/paint/web/tests/frontend-behavior.test.mjs
npm run typecheck
npm run build
```

Tests that reopen DWG require a local converter configuration. Copy `work/config/converters.example.json` to an ignored local file and replace executable, font and license paths for the target machine.

## 3. Build installable plugins

```bash
bash scripts/build_release.sh
```

Expected files:

```text
dist/plugin-release/satellite-drawings-paint-plugin-0.1.0.tgz
dist/plugin-release/satellite-drawings-blanket-plugin-0.3.0.tgz
dist/plugin-release/SHA256SUMS.txt
```

Install both archives through the DSH private-plugin installer. They are separate plugins with separate IDs and routes, but they share one backend service.

## 4. Local demonstration

The development trial uses explicit development authentication and loopback-only services:

```bash
.venv/bin/python scripts/start_simple_trial.py \
  --module paint \
  --port 18890 \
  --background
```

Open the printed URL and import `fixtures/release-cases/simplified.step`. Stop the recorded trial with:

```bash
.venv/bin/python scripts/start_simple_trial.py --stop
```

Pass `--converter-config /absolute/path/to/converters.local.json` when DWG export is required.

## 5. Account-authenticated backend

Initialize a private backend root. The default security policy allows roots under `/data/qmh`; another operator-controlled parent can be supplied explicitly:

```bash
.venv/bin/python scripts/host_backend.py \
  --allowed-parent /data/qmh \
  --root /data/qmh/satellite-drawings-backend \
  init
```

Start the loopback backend:

```bash
.venv/bin/python scripts/serve_host.py \
  --config /data/qmh/satellite-drawings-backend/config.json \
  --ready-file /data/qmh/satellite-drawings-backend/ready.json \
  --port 18777
```

After each plugin is installed in DSH, retrieve its authenticated `/api/satellite-<module>/host-info` response and enroll the public information as an operator:

```bash
.venv/bin/python scripts/host_backend.py \
  --allowed-parent /data/qmh \
  --root /data/qmh/satellite-drawings-backend \
  enroll --public-info /secure/paint-host-info.json --user ACCOUNT
```

Repeat enrollment for blanket. Never commit the generated host registry, account home, private keys, browser cookies, project database or converter credentials.

## 6. GitHub publication

Commit source, curated fixtures and documentation. Keep generated TGZ/ZIP files, virtual environments, `node_modules`, runtime databases, credentials and the 670 MB original assembly out of Git. Upload validated TGZ/ZIP files as GitHub Release assets and publish their SHA256 values.

Before calling a deployment accepted, run installation and import/export checks against the actual DSH account environment. The existing release has build and private-installer verification, but not live `9999` acceptance.
