#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is required to build the AURA desktop package." >&2
  echo "Install pnpm, run 'pnpm -w install', then rerun this script." >&2
  exit 2
fi

python infra/scripts/private_alpha_check.py

cd apps/desktop
pnpm build
pnpm exec electron-builder --config electron-builder.yml
