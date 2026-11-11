# DSH Satellite Paint and Blanket Drawings

DSH plugins and a shared Python service for satellite paint-protection drawings and multilayer blanket drawings.

- Paint plugin: `@satellite-drawings/paint-plugin` `0.1.0`
- Blanket plugin: `@satellite-drawings/blanket-plugin` `0.3.0`
- Target host: DSH `0.2.2-rc.1`, known host commit `102617dbbb4a20b445bc66fc0790c1ea3488137b`
- Supported Node.js: `^22.19.0 || >=24`
- Python: `3.12`

## Repository layout

| Path | Purpose |
| --- | --- |
| `plugins/paint/` | Paint plugin and browser workbench |
| `plugins/blanket/` | Blanket plugin and browser workbench |
| `service/` | Shared authenticated drawing service |
| `packages/geometry-core/` | STEP/XCAF geometry implementation used by the service |
| `packages/host-bridge/` | DSH host registration, proxy and MCP tools |
| `fixtures/release-cases/` | Curated demonstration and reference inputs |
| `fixtures/synthetic/`, `fixtures/real-derived/` | Automated geometry and workflow fixtures |
| `tests/` | Python, Node and browser regression tests |
| `scripts/build_release.sh` | Reproducible two-plugin build and pack entrypoint |

## Quick start

Install Node.js 22.19 or newer, npm, Python 3.12 and `uv`, then run:

```bash
uv sync --frozen --python 3.12
npm ci
npm run typecheck
npm run build
bash scripts/build_release.sh
```

The two installable archives are written to `dist/plugin-release/`. Detailed development, test and deployment instructions are in [DEVELOPMENT.md](DEVELOPMENT.md).

For the demonstrated paint workflow, use `fixtures/release-cases/simplified.step`. The engineer-provided reference drawing and requirements are stored beside it. The 670 MB original assembly and the catch assembly are intentionally not committed: they are optional external acceptance inputs, not the default demo.

## Deployment boundary

The repository is sufficient to modify, test and build both plugins and the shared backend. Production deployment still requires infrastructure that cannot be committed safely:

- a DSH account/private-plugin installer and operator approval;
- backend public-key enrollment for each plugin and account;
- a private writable backend data directory;
- OpenCADStudio or another configured DWG converter for native DWG output;
- deployment-specific paths and credentials.

The current production host path defaults to `http://127.0.0.1:18777`. The account-host proxy currently limits one request to 64 MiB and uses a 30 second default request timeout. Large STEP acceptance must be performed in the target environment.

The private installer workflow was verified with the packed paint `0.1.0` and blanket `0.3.0` archives. Live `9999` installation acceptance has not been completed, so a successful source build must not be presented as production acceptance.

## Release provenance

This source line is based on release commit `5bb1900a271ec5b5bc58f604e96ce089eea15632`. Its parent freeze commit captured the complete previously dirty working tree rather than rebuilding from the older source HEAD alone.
