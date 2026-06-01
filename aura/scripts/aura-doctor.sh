#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/apps/backend/src${PYTHONPATH:+:$PYTHONPATH}"

pass() { printf '✓ %s\n' "$1"; }
warn() { printf '! %s\n' "$1"; }
fail() { printf '✗ %s\n' "$1"; exit 1; }

echo "Aegisure Doctor"
echo "Repo: $ROOT"

command -v node >/dev/null || fail "Node.js is missing"
pass "Node $(node --version)"

command -v pnpm >/dev/null || fail "pnpm is missing. Install with: corepack enable && corepack prepare pnpm@latest --activate"
pass "pnpm $(pnpm --version)"

command -v python3 >/dev/null || fail "python3 is missing"
pass "Python $(python3 --version 2>&1)"

if [[ -d node_modules ]]; then
  pass "node_modules present"
else
  warn "node_modules missing. Run: pnpm install"
fi

pnpm aura:verify-electron >/tmp/aura-doctor-electron.log 2>&1 && pass "Electron/esbuild verified" || {
  cat /tmp/aura-doctor-electron.log
  fail "Electron/esbuild verification failed. Try: pnpm approve-builds --all && pnpm rebuild electron esbuild"
}

(cd apps/backend && python3 -m compileall -q src) && pass "Backend compile check passed"

python3 - <<'PY'
import pathlib
from storage.db import init_db
from storage.profile_paths import profile_dir
init_db()
print(profile_dir())
PY
pass "Memory database initializes"

if command -v ollama >/dev/null; then
  pass "Ollama installed"
  if curl -fsS http://localhost:11434/api/tags >/tmp/aura-doctor-ollama.json 2>/dev/null; then
    pass "Ollama running"
  else
    warn "Ollama installed but not running. Start the Ollama app or run: ollama serve"
  fi
else
  warn "Ollama missing. Aegisure will use local fallback until Ollama is installed."
fi

if [[ -f apps/desktop/release/Aegisure-1.0.0-mac-arm64.dmg ]]; then
  pass "DMG artifact exists: apps/desktop/release/Aegisure-1.0.0-mac-arm64.dmg"
else
  warn "DMG artifact missing. Build with: pnpm aura:package"
fi

echo "macOS permissions to verify manually: Accessibility, Automation, Microphone, Screen Recording if using visual context."
echo "Aegisure Doctor complete."
