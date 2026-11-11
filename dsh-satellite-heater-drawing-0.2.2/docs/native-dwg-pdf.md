# Native DWG and PDF generation

The native delivery profile is `dwg_pdf_v1`. It uses the existing controlled
heater template and 17-column Excel contract. Excel is authoritative when the
reference drawings disagree with a field (including `Sheet1!O3`, 郑玲).

## Run on 5090

From `/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing`:

```sh
.venv/bin/python scripts/generate_heaters.py \
  --input fixtures/case/加热器图纸.xlsx \
  --name 加热器图纸 \
  --output /path/to/a/new/delivery-directory
```

The output directory must not exist. The engine validates every row, creates
an immutable revision, plans and checks all pages, saves editable DWG 2018,
reopens the DWG, performs a verified reverse DXF save and strict semantic
readback, and plots each page from that reopened DWG. It then merges pages
in Excel order and independently reopens/replots the delivered DWG before
publishing the complete package atomically. Failure publishes no partial set.

Outputs include one DWG, one source DXF, `pdf/<代号>.pdf`, a merged PDF, the
original/actual Excel workbooks, `revision.json`, `row-report.json`,
`cad-report.json`, a hash manifest, a run record and a ZIP.

The engine does not silently change scales or skip invalid rows. Existing
explicitly confirmed revision/skip workflows remain available through
`build_delivery`; a revision selecting `dwg_pdf_v1` uses native delivery.
Legacy `dxf_pdf_v1` revisions retain the previous DXF/Matplotlib path.

## Runtime configuration

- `HEATER_OPENCADSTUDIO`: native executable, default
  `/data/qmh/OpenCADStudio/current/squashfs-root/usr/bin/OpenCADStudio`.
  Do not point this at the installation's shell wrapper, which replaces XDG
  directories and would defeat per-run isolation.
- `HEATER_HZDX_FONT`: optional external path to the engineer-supplied
  HZDX.SHX. The default is the resource root's `fixtures/case/HZDX.SHX`.
  The file must match the controlled SHA-256. It is copied only into a private
  temporary CAD font folder; no global CAD settings are changed.
- Native dimensions request the sample's TXT SHX font, width 0.85 and
  5 mm paper character height (model height scales with the denominator).
  Sample arrows are 2.5 mm, or 2.0 mm for KX-11-WR-100-300-M1. The original
  template files/manifests remain immutable; the versioned native output
  profile applies these style settings. The locked Noto SC face remains the
  conservative planning/coverage metric face and is copied into the private
  runtime; it no longer replaces the visible native dimension digits.

Native dimension lines also use the sample's above-line text, 0.625 mm
extension origin gap and 1.25 mm extension beyond the dimension line.
The input materials do not include the original `txt.shx` binary, so
OpenCADStudio currently resolves this font through its built-in substitute;
individual Latin/digit glyph outlines may differ from AutoCAD's sample.
HZ Chinese glyphs use the supplied original HZDX file. In spaced fixed labels,
the substitute advances ASCII spaces too widely. The native profile stores
the footer, phase-mark and change-number glyphs as separate editable TEXT
entities at the sample's positions. PDF footer and phase-mark glyph bounds
are tested to prevent overlaps/clipping.

Native delivery also restores the technical block's original position and
eight requirement lines. Its actual HZ glyph bounds are measured with an
isolated CAD vector plot, rather than the wider Noto substitute. A coloured
10 mm calibration square recovers the real PDF transform; all visible black
glyph paths, including zero-area single strokes, contribute to the bounds.
Probes touching the measurement-page boundary fail. Results are cached by
text/style and the native executable identity. Overflowing variable quantity
text still blocks publication. Other template fields retain the conservative
locked-font checks.

No runtime imports or modifies another plugin. The drawings plugin's native
session/save/readback design was used as a reference, not as a dependency.

## Printing policy

The user chose the sample's printed appearance rather than correcting its
approximately 4.2% enlargement. Geometry and dimension values stay at true
model size; the per-page print scale is `1.041982 / scale_denominator`.
The frame window comes from the controlled template, with full-bleed A4,
fixed offsets `(0.7056, 1.0335888889)` mm and the native monochrome plot style.
This retains the original true-colour yellow frame.

OpenCADStudio 2026.45 ignores CTB lineweight overrides for the true-colour
yellow frame. `plot_style.py` therefore applies the sample's uniform physical
0.72 pt stroke width to the resulting vector PDF, accounting for PDF graphics
transforms. Coordinates, colours, fills and text remain unchanged. The report
records hashes before/after this printing pass and the applied policy. It
fails on unsupported non-uniform transforms or XObjects instead of guessing.

Two interoperability fixes are covered by regression tests: all generated
paper viewports reference the declared `0` layer, and dimension-cache MTEXT
orientation is compared by effective normalized direction (rotation and
direction-vector encodings are equivalent).

## Verification and scope

`cad-report.json` contains the actual native save/reverse-save audit, geometry
and text readback, font hashes, per-page plot settings and source DWG binding.
The native integration tests use the real installed application, including a
damaged DWG with rebound hashes and a missing-executable failure.

This implements the native drawing/delivery engine. The pre-existing B06
service, B07 DSH Host/MCP, B08 workbench and B09 engineering review are separate
unimplemented milestones; no installed DSH integration or AutoCAD review is
claimed by a successful native engine run.
