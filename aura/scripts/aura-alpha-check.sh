#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Aegisure alpha-check"
pnpm aura:doctor
python3 infra/scripts/private_alpha_check.py
pnpm aura:demo-check
echo "Aegisure alpha-check passed."
