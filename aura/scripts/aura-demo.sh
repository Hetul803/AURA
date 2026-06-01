#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Running demo readiness check, then starting Aegisure."
pnpm aura:demo-check
exec bash scripts/aura-dev.sh
