#!/usr/bin/env bash
set -euo pipefail

DMG_PATH="${1:-apps/desktop/release/Aegisure-1.0.0-mac-arm64.dmg}"

if [[ ! -f "$DMG_PATH" ]]; then
  echo "DMG not found: $DMG_PATH"
  exit 1
fi

if [[ -z "${APPLE_ID:-}" || -z "${APPLE_TEAM_ID:-}" || -z "${APPLE_APP_SPECIFIC_PASSWORD:-}" ]]; then
  cat <<'EOF'
Missing notarization credentials.

Set:
  APPLE_ID
  APPLE_TEAM_ID
  APPLE_APP_SPECIFIC_PASSWORD

Then run:
  scripts/notarize-mac.sh apps/desktop/release/Aegisure-1.0.0-mac-arm64.dmg

You also need a valid Developer ID Application certificate available to electron-builder before packaging.
EOF
  exit 2
fi

echo "Submitting $DMG_PATH for Apple notarization..."
xcrun notarytool submit "$DMG_PATH" \
  --apple-id "$APPLE_ID" \
  --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_SPECIFIC_PASSWORD" \
  --wait

echo "Stapling notarization ticket..."
xcrun stapler staple "$DMG_PATH"
echo "Notarized and stapled: $DMG_PATH"
