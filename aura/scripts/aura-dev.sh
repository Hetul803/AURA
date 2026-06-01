#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Aegisure one-command start"
echo "    Working directory: $ROOT"
echo "    Expected command: cd Aegisure/aura && ./start-aegisure.sh"
echo

if [[ ! -d node_modules || ! -d apps/desktop/node_modules || ! -x apps/backend/.venv/bin/python ]]; then
  echo "==> Dependencies are missing or incomplete; running installer"
  bash scripts/aura-install.sh
else
  echo "==> Dependencies found; verifying Electron/esbuild"
  pnpm rebuild electron esbuild >/dev/null
fi

PORT="${AEGISURE_BACKEND_PORT:-8000}"
BACKEND_URL="http://127.0.0.1:${PORT}"
BACKEND_PID=""

cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1; then
  echo "==> Aegisure backend already running at ${BACKEND_URL}"
else
  echo "==> Starting Aegisure backend at ${BACKEND_URL}"
  apps/backend/.venv/bin/python -m uvicorn api.main:app --app-dir apps/backend/src --host 127.0.0.1 --port "$PORT" &
  BACKEND_PID="$!"
  for _ in {1..40}; do
    if curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
      echo "Backend exited before becoming healthy." >&2
      echo "Try: pnpm aura:backend" >&2
      exit 2
    fi
    sleep 0.25
  done
fi

if ! curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1; then
  echo "Backend did not become healthy at ${BACKEND_URL}." >&2
  echo "Run pnpm aura:backend in another terminal to inspect backend logs." >&2
  exit 2
fi

echo "==> Starting Aegisure desktop"
echo "Backend: ${BACKEND_URL}"
echo "If Electron fails after a fresh clone, run: pnpm approve-builds --all && pnpm rebuild electron esbuild"
echo "Quit the desktop app or press Ctrl+C here to stop the dev session."
export AEGISURE_BACKEND_URL="$BACKEND_URL"
pnpm --filter aura-desktop dev
