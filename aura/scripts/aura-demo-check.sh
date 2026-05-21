#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PROFILE_DIR_OVERRIDE="${PROFILE_DIR_OVERRIDE:-$(mktemp -d /tmp/aura-demo-profile.XXXXXX)}"

echo "AURA demo-check: Guardian + Memory + Identity + helper primitives"
(cd "$ROOT/apps/backend" && pytest -q \
  tests/test_guardian_core_loop.py \
  tests/test_memory_engine.py \
  tests/test_identity_boundary.py \
  tests/test_private_alpha_check.py)

echo "Renderer unit checks"
(cd "$ROOT/apps/desktop" && pnpm test)

echo "Demo-check passed."
