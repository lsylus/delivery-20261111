# OpenCADStudio DWG export and actual application preview

The `opencadstudio` adapter is selected through the existing converter configuration.
5090's ready configuration is `deploy/opencadstudio-5090.json`. Set the service's
existing `converter_config` setting to that absolute path; the existing
`drawing.export` worker uses the adapter without another route or service.

The executable intentionally points at the native binary below the installed
`current` link. The installed `bin/OpenCADStudio` wrapper overrides XDG paths
with the shared installation profile and is rejected by this adapter. Each export
starts its own official `--serve` channel with temporary private XDG directories.
No shared software installation settings, existing GUI, or web service are changed.

The adapter validates the source DXF, calls official `save_verified` for DWG
2018, explicitly reopens that DWG, rejects missing fonts, verified-saves a reverse
DXF, and checks every source entity's geometry, layer, editable dimensions, text,
document metadata and entity XDATA at the existing 1e-6 mm fixture tolerance.
The DWG and readback files publish only after these checks. Existing paths are
never overwritten.

## Known v2026.45 interoperability difference

The official DWG and reverse DXF saves both report verified, lossless success.
The reverse DXF includes owner-zero TABLESTYLE records which ezdxf audit deletes.
The adapter retains original `drawing.readback.dxf` bytes, records every such
diagnosed repair in `conversion.json`, and saves
`drawing.readback.validated.dxf` for the unchanged strict project validator.
Only error code 202 for a TABLESTYLE actually found with owner 0 is admitted;
all other audit fixes/errors fail. No model-space entity is normalized and the
actual DWG is never rewritten. This is reported as an interoperability warning,
not a claim that the raw reverse DXF needed no repair.

## Preview the actual delivered DWG

From the repository root on 5090:

```sh
.venv/bin/python scripts/opencad_preview.py \
  PATH/TO/drawing.dwg PATH/TO/preview.png \
  --config deploy/opencadstudio-5090.json
```

This launches a private Xvfb display and real native editor using official MCP,
opens the DWG, audits geometry and text, then captures the actual application
viewport. The adjacent `preview.preview.json` binds the capture to the input
DWG SHA-256 and includes audit/text/font evidence. Output paths must be new.
The CPU renderer may show an application GPU notice in the captured viewport.
The CLI does not use the installed web server or other users' editor sessions.

For any of the cube, cylinder and cube-cylinder samples, first run the existing
`drawing.export` command against the current generated revision with the config
above; then pass the downloaded/published DWG to this same preview command.
Do not substitute a different sample's DWG when a current generated revision
changes.

## Focused checks

```sh
THERMAL_OPENCADSTUDIO=/data/qmh/OpenCADStudio/current/squashfs-root/usr/bin/OpenCADStudio \
  .venv/bin/python -m pytest -q tests/formats/test_opencadstudio.py \
  tests/formats/test_dwg_adapter.py tests/formats/test_dxf_roundtrip.py
```

Observed real evidence is in `work/thermal-simple-opencad/adapter/`:
`drawing.dwg`, both reverse DXFs, `conversion.json`, `preview.png`, and
`preview.preview.json`. Chinese text, hatch islands, circles/arcs, polylines
and editable 60/100 mm dimensions survived export and reopen. This verifies
OpenCADStudio interoperability for the tested documents; independent AutoCAD
and engineering approval remain separate from this software preview.

## Optional preview in the existing export operation

Send parameters `{result_id, draft: true, preview: true}` to the existing
`drawing.export` operation. The real application PNG is published in the same
run with `role: drawing_preview`, `format: PNG`, and `mime_type: image/png`.
Its `dwg-preview-binding` validation records the exact source DWG SHA-256 and
revision. Publication independently rechecks PNG bytes and both hashes.

`preview-status.json` reports `ready` or `unavailable`; `conversion.json.preview`
contains the same result. A failed optional renderer preserves the verified DWG
and exports it normally. Omitting `preview` retains the existing export behavior.
The renderer lives in the installed `thermal_drawings.drawing.opencad_preview`
module; the script is a convenience wrapper. Worker invocations inherit the
worker process group so cancellation terminates the GUI and Xvfb descendants.

Preview defaults to the official `BACKGROUND White` display command without
resaving or changing the DWG. CLI `--bounds min_x min_y max_x max_y` permits
a second local capture, and `--background current` preserves the default view.
