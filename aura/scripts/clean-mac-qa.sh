#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DESTRUCTIVE=0
if [[ "${1:-}" == "--reset-local-state" ]]; then
  DESTRUCTIVE=1
fi

echo "Aegisure clean-Mac QA"
echo "Root: $ROOT"
echo

require_file() {
  if [[ -e "$1" ]]; then
    echo "[ok] $2"
  else
    echo "[fail] $2 missing: $1"
    exit 1
  fi
}

require_command() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "[ok] $2"
  else
    echo "[fail] $2 missing. Install $1 first."
    exit 1
  fi
}

require_file start-aegisure.sh "one-command start script"
require_file package.json "repo package manifest"
require_file apps/web/src/server.js "website/download server"
require_file apps/desktop/electron-builder.yml "desktop package config"
require_command node "Node.js"
require_command pnpm "pnpm"
require_command python3 "Python 3"

echo
echo "Checking launch scripts..."
pnpm aura:doctor
pnpm aura:alpha-check

echo
echo "Checking web launch server tests..."
pnpm --filter aegisure-web test

DMG="apps/desktop/release/Aegisure-1.0.0-mac-$(uname -m | sed 's/aarch64/arm64/;s/x86_64/x64/').dmg"
if [[ -f "$DMG" ]]; then
  echo "[ok] DMG already built: $DMG"
else
  echo "[warn] DMG not found. Run pnpm aura:package before install QA."
fi

if (( DESTRUCTIVE == 1 )); then
  ARCHIVE="$HOME/AEGISURE_CLEAN_MAC_QA_ARCHIVE_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$ARCHIVE"
  echo
  echo "Archiving local installed/app state to: $ARCHIVE"
  [[ -d "/Applications/Aegisure.app" ]] && mv "/Applications/Aegisure.app" "$ARCHIVE/Aegisure.app" || true
  [[ -d "$HOME/Library/Application Support/aura-desktop" ]] && mv "$HOME/Library/Application Support/aura-desktop" "$ARCHIVE/aura-desktop-support" || true
  [[ -d "$HOME/Library/Logs/aura-desktop" ]] && mv "$HOME/Library/Logs/aura-desktop" "$ARCHIVE/aura-desktop-logs" || true
  [[ -d "$HOME/.aura" ]] && mv "$HOME/.aura" "$ARCHIVE/dot-aura" || true
  echo "[ok] Local Aegisure state archived. Open the DMG and test like a new user."
else
  cat <<'EOF'

Dry run complete.

For true clean-Mac QA after confirming your work is pushed, run:
  scripts/clean-mac-qa.sh --reset-local-state

Then:
  pnpm aura:package
  open apps/desktop/release/Aegisure-1.0.0-mac-arm64.dmg

Expected first-user result:
  - onboarding opens;
  - license panel can activate a signed token;
  - update/crash diagnostics are visible;
  - overlay can be shown;
  - Guardian, Memory, Identity, clone/draft/coding-job demos work.
EOF
fi
