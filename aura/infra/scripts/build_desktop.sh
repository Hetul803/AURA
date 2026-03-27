#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DESKTOP_DIR="$ROOT_DIR/apps/desktop"

cd "$DESKTOP_DIR"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to build/package the desktop app." >&2
  exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "dist:mac must be run on macOS to produce the private-alpha DMG artifacts." >&2
  exit 1
fi

npm install
npm run dist:mac
