#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PROFILE_DIR_OVERRIDE="${PROFILE_DIR_OVERRIDE:-$(mktemp -d /tmp/aura-smoke-profile.XXXXXX)}"

echo "AURA private-alpha smoke"
echo "Repo: $ROOT"
echo "Profile: $PROFILE_DIR_OVERRIDE"

echo "1/5 Backend compile"
(cd "$ROOT/apps/backend" && python3 -m compileall -q src)

echo "2/5 Guardian, Memory, Identity backend tests"
(cd "$ROOT/apps/backend" && pytest -q \
  tests/test_guardian_core_loop.py \
  tests/test_completion_product_features.py \
  tests/test_memory_engine.py \
  tests/test_identity_boundary.py \
  tests/test_workflow_engine.py \
  tests/test_private_alpha_check.py)

echo "3/5 Desktop tests"
(cd "$ROOT/apps/desktop" && pnpm test)

echo "4/5 Desktop build"
(cd "$ROOT/apps/desktop" && pnpm build)

echo "5/5 Electron install verification"
(cd "$ROOT" && pnpm aura:verify-electron)

echo "AURA smoke passed."
