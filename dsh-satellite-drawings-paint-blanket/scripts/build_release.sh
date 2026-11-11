#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/dist/plugin-release}"

cd "$ROOT"
node -e "const major=Number(process.versions.node.split('.')[0]); if (major < 22) throw new Error('Node.js 22.19 or newer is required')"
npm ci
npm run typecheck
npm run build

mkdir -p "$OUT"
npm pack --workspace @satellite-drawings/paint-plugin --pack-destination "$OUT"
npm pack --workspace @satellite-drawings/blanket-plugin --pack-destination "$OUT"

(
  cd "$OUT"
  sha256sum satellite-drawings-paint-plugin-0.1.0.tgz satellite-drawings-blanket-plugin-0.3.0.tgz > SHA256SUMS.txt
  sha256sum -c SHA256SUMS.txt
)

printf 'Release archives written to %s\n' "$OUT"
