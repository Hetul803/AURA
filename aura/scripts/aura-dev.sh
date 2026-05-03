#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d node_modules || ! -d apps/desktop/node_modules || ! -x apps/backend/.venv/bin/python ]]; then
  bash scripts/aura-install.sh
else
  pnpm rebuild electron esbuild >/dev/null
fi

PORT="${AURA_BACKEND_PORT:-8000}"
BACKEND_URL="http://127.0.0.1:${PORT}"
BACKEND_PID=""

cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1; then
  echo "==> AURA backend already running at ${BACKEND_URL}"
else
  echo "==> Starting AURA backend at ${BACKEND_URL}"
  apps/backend/.venv/bin/python -m uvicorn api.main:app --app-dir apps/backend/src --host 127.0.0.1 --port "$PORT" &
  BACKEND_PID="$!"
  for _ in {1..40}; do
    if curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
      echo "Backend exited before becoming healthy." >&2
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

echo "==> Starting AURA desktop"
echo "Backend: ${BACKEND_URL}"
echo "Quit the desktop app or press Ctrl+C here to stop the dev session."
export AURA_BACKEND_URL="$BACKEND_URL"
pnpm --filter aura-desktop dev
