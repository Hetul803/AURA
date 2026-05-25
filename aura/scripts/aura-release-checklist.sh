#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DMG="${1:-apps/desktop/release/AURA-1.0.0-mac-$(uname -m | sed 's/aarch64/arm64/;s/x86_64/x64/').dmg}"

ok=0
warn=0

pass() { printf '[ok] %s\n' "$1"; ok=$((ok + 1)); }
note() { printf '[warn] %s\n' "$1"; warn=$((warn + 1)); }
fail() { printf '[fail] %s\n' "$1"; warn=$((warn + 1)); }

echo "AURA production release checklist"
echo "Root: $ROOT"
echo

[[ -f package.json ]] && pass "repo root package.json present" || fail "run from repo root"
[[ -f "$DMG" ]] && pass "DMG artifact exists: $DMG" || note "DMG not built yet. Run pnpm aura:package"
[[ -f infra/releases/releases.json ]] && pass "release metadata present" || fail "missing infra/releases/releases.json"
[[ -f apps/desktop/electron-builder.yml ]] && pass "electron-builder config present" || fail "missing Electron packaging config"

if command -v xcrun >/dev/null 2>&1; then
  pass "xcrun available for notarization checks"
else
  note "xcrun missing. Install Xcode Command Line Tools before signing/notarization"
fi

if security find-identity -v -p codesigning 2>/dev/null | grep -q "Developer ID Application"; then
  pass "Developer ID Application signing identity found in keychain"
else
  note "No Developer ID Application identity found. Unsigned builds are only for local/private testing"
fi

for key in APPLE_ID APPLE_TEAM_ID APPLE_APP_SPECIFIC_PASSWORD; do
  if [[ -n "${!key:-}" ]]; then pass "$key configured"; else note "$key not set"; fi
done

if [[ -z "${CSC_NAME:-}" && -z "${CSC_LINK:-}" ]]; then
  detected_identity="$(security find-identity -v -p codesigning 2>/dev/null | sed -n 's/.*"Developer ID Application: \(.*([^)]*)\)".*/\1/p' | head -1 || true)"
  if [[ -n "$detected_identity" ]]; then
    export CSC_NAME="$detected_identity"
  fi
fi

if [[ -n "${CSC_NAME:-}" || -n "${CSC_LINK:-}" ]]; then
  pass "Electron signing identity/certificate env configured"
else
  note "Set CSC_NAME or CSC_LINK/CSC_KEY_PASSWORD before production signing"
fi

for key in PUBLIC_BASE_URL STRIPE_SECRET_KEY STRIPE_PRICE_ID STRIPE_WEBHOOK_SECRET AURA_VENDOR_PRIVATE_KEY AURA_VENDOR_PUBLIC_KEY AURA_ADMIN_TOKEN AURA_DOWNLOAD_MAC_URL; do
  if [[ -n "${!key:-}" ]]; then pass "$key configured"; else note "$key not set"; fi
done

if [[ -x scripts/notarize-mac.sh ]]; then pass "notarization script executable"; else fail "scripts/notarize-mac.sh is not executable"; fi
if [[ -x scripts/package-production-mac.sh ]]; then pass "production packaging script executable"; else fail "scripts/package-production-mac.sh is not executable"; fi

echo
echo "Checklist summary: $ok passing checks, $warn warnings."
if (( warn > 0 )); then
  cat <<'EOF'

Warnings are expected on a development Mac without Apple/Stripe production secrets.
For real public distribution, clear every warning, build with pnpm aura:package:prod,
then upload the notarized DMG to the URL configured as AURA_DOWNLOAD_MAC_URL.
EOF
fi
