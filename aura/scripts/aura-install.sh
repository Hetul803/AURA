#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

need_command() {
  local cmd="$1"
  local help="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing $cmd." >&2
    echo "$help" >&2
    exit 2
  fi
}

need_command node "Install Node.js 20 LTS or newer, then rerun ./start-aura.sh."
node - <<'NODE'
const major = Number(process.versions.node.split('.')[0]);
if (major < 18) {
  console.error(`AURA needs Node.js 18+; found ${process.version}. Install Node.js 20 LTS or newer.`);
  process.exit(2);
}
NODE

need_command pnpm "Install pnpm with: corepack enable pnpm  OR  npm install -g pnpm"

if [[ ! -d node_modules || ! -d apps/desktop/node_modules ]]; then
  echo "==> Installing pnpm workspace dependencies"
  pnpm install
else
  echo "==> pnpm dependencies already present"
fi

echo "==> Ensuring pnpm v10 allows Electron/esbuild build scripts"
pnpm rebuild electron esbuild || {
  echo "Electron/esbuild rebuild failed." >&2
  echo "If pnpm blocked build scripts, run: pnpm approve-builds --all" >&2
  echo "Then rerun: pnpm rebuild electron esbuild" >&2
  exit 2
}

pnpm aura:verify-electron

need_command python3 "Install Python 3.10+ from python.org, Homebrew, or Xcode command line tools."

if [[ ! -d apps/backend/.venv ]]; then
  echo "==> Creating backend virtual environment"
  python3 -m venv apps/backend/.venv
fi

echo "==> Installing backend dependencies"
apps/backend/.venv/bin/python -m pip install --upgrade pip >/dev/null
apps/backend/.venv/bin/python -m pip install -e apps/backend

echo "AURA developer dependencies are ready."
