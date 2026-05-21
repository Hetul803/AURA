#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "AURA alpha-check"
pnpm aura:doctor
python3 infra/scripts/private_alpha_check.py
pnpm aura:demo-check
echo "AURA alpha-check passed."
