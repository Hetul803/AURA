#!/usr/bin/env bash
set -euo pipefail
(cd apps/backend && uvicorn src.api.main:app --reload --port ${BACKEND_PORT:-8000}) &
(cd apps/web && node src/server.js) &
wait
