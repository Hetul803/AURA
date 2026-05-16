#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/apps/desktop/native/macos/AURASpeechHelper.swift"
OUT_DIR="$ROOT/apps/desktop/native/macos/build"
OUT="$OUT_DIR/AURASpeechHelper"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS speech helper can only be built on macOS."
  exit 0
fi

if ! command -v swiftc >/dev/null 2>&1; then
  cat <<'EOF'
swiftc is not installed.

Install Xcode or Apple Command Line Tools, then rerun:
  scripts/build-macos-speech-helper.sh

AURA will still work with typed commands and macOS speech output.
EOF
  exit 0
fi

mkdir -p "$OUT_DIR"
swiftc "$SRC" -o "$OUT" -framework Speech -framework AVFoundation
chmod +x "$OUT"
echo "Built native speech helper: $OUT"

