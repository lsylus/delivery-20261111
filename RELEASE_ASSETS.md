# Release assets on 5090

These files are intentionally outside the Git commit and should be uploaded through GitHub Releases.

## Paint and blanket

Latest installable archives with the right-sidebar entries and UTF-8 STEP upload
filename support:

`/data/qmh/satellite-plugins-20261029/delivery-20261111/dsh-satellite-drawings-sidebar-20261111/plugins`

- `satellite-drawings-paint-plugin-0.1.0.tgz`
  SHA256 `1ee4418b0178368269b294ab0ba9fac74719aed28418d519952e216c7f1fa375`
- `satellite-drawings-blanket-plugin-0.3.0.tgz`
  SHA256 `d6301207a997e2a59be075734bd5ec4a1a75aef62b735d9bace5a508ec090280`

Historical unified delivery directory:

`/data/qmh/satellite-plugins-20261029/delivery-20261111/dsh-satellite-drawings-paint-0.1.0-blanket-0.3.0`

Unified ZIP:

- `dsh-satellite-drawings-paint-0.1.0-blanket-0.3.0.zip`
- SHA256 `e4d5ace2756c18f0fc120a923f05e79a140c72084dbd4421415a8cb2573b357e`

The historical directory also contains earlier paint `0.1.0` and blanket `0.3.0`
TGZ files, source archive, manifest and `SHA256SUMS.txt`. Do not publish those
earlier TGZ files as the latest plugin assets.

## Heater

Source archive:

- `/data/qmh/satellite-plugins-20261029/delivery-20261111/dsh-satellite-heater-drawing-0.2.2-github-source.tar.gz`
- SHA256 `8a5e5915e306403f5e286464035428b7a28871ca8550987cd37b02e0cc973430`

Heater plugin release packages remain under the heater project's ignored `dist/` directory. Verify their current hashes before attaching them to a GitHub Release.
