#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${OSTYPE:-}" != darwin* ]]; then
  echo "AURA macOS DMG packaging must run on macOS." >&2
  exit 2
fi

bash scripts/aura-install.sh
python infra/scripts/private_alpha_check.py

echo "==> Building macOS DMG"
pnpm --filter aura-desktop package

EXPECTED="apps/desktop/release/AURA-1.0.0-mac-$(uname -m | sed 's/aarch64/arm64/;s/x86_64/x64/').dmg"
if [[ -f "$EXPECTED" ]]; then
  echo "DMG ready: $EXPECTED"
else
  echo "DMG build finished. Artifacts:" >&2
  find apps/desktop/release -maxdepth 2 -type f -name 'AURA-*.dmg' -print >&2
fi
