# Satellite drawing plugins delivery

This repository contains the source for the satellite drawing plugins prepared on 2026-11-11.

## Projects

| Directory | Versions | Purpose |
| --- | --- | --- |
| `dsh-satellite-drawings-paint-blanket/` | paint `0.1.0`, blanket `0.3.0` | STEP-based paint-protection and multilayer blanket drawings |
| `dsh-satellite-heater-drawing-0.2.2/` | heater `0.2.2` | Excel-driven rectangular-heater DWG/PDF generation |

Each project has its own README, development instructions, lock files, tests and release build entrypoint. Start with the project-specific documentation rather than assuming the two services share runtime dependencies.

The paint/blanket repository includes the compact `simplified.step` demonstration, engineer-provided paint DWG, engineering requirements and automated synthetic/derived fixtures. The 670 MB original satellite assembly and the catch assembly are external acceptance inputs and are intentionally not committed.

## Release assets

Generated ZIP, TGZ and source archives are kept beside this repository on the 5090 build host and are excluded from Git. Upload them to a GitHub Release instead of committing them to the source branch. Exact current paths and checksums are listed in [RELEASE_ASSETS.md](RELEASE_ASSETS.md).

## Publication

This root is the Git repository to publish. After adding a GitHub remote, push branch `main`. Do not initialize or publish the child directories as separate repositories unless the projects are intentionally split later.

Production deployment still requires the target DSH private-plugin installer, account authorization, private backend state and external CAD/font resources. No credentials, account data or runtime databases belong in this repository.
