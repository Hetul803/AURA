#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x apps/backend/.venv/bin/python ]]; then
  bash scripts/aura-install.sh
fi

PORT="${AEGISURE_BACKEND_PORT:-8000}"
echo "==> Starting Aegisure backend on http://127.0.0.1:${PORT}"
exec apps/backend/.venv/bin/python -m uvicorn api.main:app --app-dir apps/backend/src --host 127.0.0.1 --port "$PORT"
