#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

missing=()
for key in APPLE_ID APPLE_TEAM_ID APPLE_APP_SPECIFIC_PASSWORD; do
  [[ -n "${!key:-}" ]] || missing+=("$key")
done

if [[ -z "${CSC_NAME:-}" && -z "${CSC_LINK:-}" ]]; then
  detected_identity="$(security find-identity -v -p codesigning 2>/dev/null | sed -n 's/.*"Developer ID Application: \(.*([^)]*)\)".*/\1/p' | head -1 || true)"
  if [[ -n "$detected_identity" ]]; then
    export CSC_NAME="$detected_identity"
    echo "Using detected Developer ID signing identity: $CSC_NAME"
  fi
fi

if [[ -z "${CSC_NAME:-}" && -z "${CSC_LINK:-}" ]]; then
  missing+=("CSC_NAME or CSC_LINK")
fi

if (( ${#missing[@]} )); then
  printf 'Missing production signing/notarization env vars:\n'
  printf '  %s\n' "${missing[@]}"
  cat <<'EOF'

Set the values from .env.example after creating an Apple Developer ID certificate.
Unsigned builds are fine for local testing, but not for real users.
EOF
  exit 2
fi

echo "Running release checklist..."
scripts/aura-release-checklist.sh || true

echo "Building native macOS speech helper..."
scripts/build-macos-speech-helper.sh

echo "Building signed DMG..."
pnpm aura:package

echo "Submitting DMG for notarization..."
scripts/notarize-mac.sh apps/desktop/release/AURA-1.0.0-mac-arm64.dmg

echo "Production Mac artifact ready:"
echo "  apps/desktop/release/AURA-1.0.0-mac-arm64.dmg"
