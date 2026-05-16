# Production Launch Plan

This is the remaining path from private alpha to a real paid launch.

## 1. Voice

Use a two-layer voice stack:

1. **Speech output:** macOS `say` for local private alpha. It is native, offline, no API key, no cloud dependency, and already wired into the desktop app with selectable system voices.
2. **Speech input:** move away from browser Web Speech. Recommended path:
   - Short term: Apple Speech framework through a native helper for macOS. Best user experience on Mac, but review Apple terms and permission UX.
   - Local/offline path: `whisper.cpp` with a bundled or user-downloaded Whisper model. It is strong for privacy and cross-platform. Check model licenses before bundling. Safer private-alpha posture: download model after user approval.
   - Avoid cloud-only STT as the default because AURA’s moat is private/local identity.

Recommended implementation: native helper service for macOS that exposes push-to-talk transcription over localhost IPC, with Whisper fallback for users who want offline-only mode.

## 2. Apple Signing And Notarization

Required before real users trust the DMG:

- Apple Developer account.
- Developer ID Application certificate.
- Developer ID Installer certificate if using PKG later.
- Notarization credentials through App Store Connect API key.
- Hardened runtime entitlements.
- Final app icon and bundle ID.

Build can be made production signed with Electron Builder once credentials are available.

## 3. Checkout And License Server

Current state:

- Desktop app verifies Ed25519-signed license tokens.
- Website has Stripe Checkout, webhook, license issuance, device activation, revocation, and crash-report scaffolding.
- Private-alpha state is stored in `AURA_WEB_DB_PATH` as a durable JSON store for a small alpha. Replace with Postgres before a broad launch.

Production path:

1. Use Stripe Checkout for payment.
2. On successful webhook, issue a signed license token.
3. Store account, device activation, token id, revocation state, and subscription status.
4. Desktop verifies license locally and can activate devices against `/api/devices/activate`.
5. Guardian must prevent license tokens from being saved as regular memory.

Required env:

```bash
STRIPE_SECRET_KEY=...
STRIPE_PRICE_ID=...
STRIPE_WEBHOOK_SECRET=...
PUBLIC_BASE_URL=https://your-domain.com
AURA_VENDOR_PRIVATE_KEY=...
AURA_VENDOR_PUBLIC_KEY=...
AURA_ADMIN_TOKEN=...
```

## 4. Crash Reporting

Private alpha:

- Local logs and renderer issue reports.

Production:

- Add opt-in crash reporting.
- Redact memory, secrets, prompts, paths, browser URLs, and selected text.
- Upload only error class, stack, app version, OS, feature area, and explicit user description unless the user opts into diagnostics bundle sharing.

## 5. Auto Update

Production:

- Code signed app.
- Release manifest endpoint.
- Differential updates through Electron updater or a custom signed manifest.
- Guardian-style update prompt explaining version, signature, and restart.

## 6. OS-Wide Guardian

Current Guardian protects AURA-managed actions. Do not claim OS-wide protection yet.

Native expansion path:

- Accessibility observer for focused app/window changes.
- ScreenCaptureKit or approved screen APIs for visual context when explicitly enabled.
- Endpoint Security framework for file/process events. This requires careful entitlement and distribution planning.
- Browser extension for website permission requests and page-level signals.
- Clipboard monitoring only after explicit opt-in.

The first launchable version should stay honest:

> Guardian protects actions AURA takes or mediates. OS-wide app and website monitoring are future native extensions.

## 7. Real User Readiness

Ready for 10 private alpha users after:

- signed/notarized macOS build;
- final product name and icon;
- tested license token checkout;
- persistent production hosting for the website/license store;
- fresh install test on clean Macs;
- native voice output verified;
- push-to-talk fallback clearly explained;
- crash/log collection process;
- support email and reset instructions.
