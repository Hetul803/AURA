# Launch Operations

This is the operator checklist for giving Aegisure to the first 10 real private-alpha users.

## 1. Configure Brand

```bash
pnpm aura:brand --product-name "YourProductName" --company-name "Your Company"
```

The assistant remains user-renameable inside the app.

## 2. Generate License Signing Keys

```bash
python scripts/generate-license-key.py --print-env
```

Put the private key only on the website/license server. Put the public key in both the website and desktop/backend environment.

## 3. Configure Website Checkout

Set:

```bash
PUBLIC_BASE_URL=https://your-domain.com
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
AEGISURE_WEB_DB_PATH=/var/lib/aura/private-alpha-store.json
AEGISURE_VENDOR_PRIVATE_KEY=...
AEGISURE_VENDOR_PUBLIC_KEY=...
AEGISURE_ADMIN_TOKEN=...
```

Routes:

- `POST /api/checkout/create`
- `POST /api/stripe/webhook`
- `POST /api/devices/activate`
- `POST /api/devices/revoke`
- `POST /api/crash-reports`
- `GET /api/updates/latest`
- `GET /api/download?os=mac`
- `GET /api/launch/health`

For the first 10 users, the durable JSON store is acceptable on one server with backups. Before broad launch, replace `AlphaStore` with Postgres.

The website serves real downloads in this order:

1. `AEGISURE_LOCAL_MAC_ARTIFACT` or `AEGISURE_LOCAL_DMG_PATH` if present on the server.
2. `apps/desktop/release/Aegisure-1.0.0-mac-arm64.dmg` for local/private testing.
3. `AEGISURE_DOWNLOAD_MAC_URL` or the URL in `infra/releases/releases.json`.

Set `AEGISURE_DOWNLOAD_MAC_URL` to the final hosted notarized DMG before inviting users.

## 4. Build Native Speech Helper

```bash
pnpm aura:voice:build
```

This compiles the macOS Apple Speech helper. If `swiftc` is unavailable, install Xcode or Apple Command Line Tools.

## 5. Build, Sign, And Notarize Mac App

Set:

```bash
APPLE_ID=founder@example.com
APPLE_TEAM_ID=TEAMID1234
APPLE_APP_SPECIFIC_PASSWORD=xxxx-xxxx-xxxx-xxxx
CSC_NAME="Developer ID Application: Your Company, Inc. (TEAMID1234)"
CSC_LINK=/secure/path/developer-id-certificate.p12
CSC_KEY_PASSWORD=...
```

Then run:

```bash
pnpm aura:package:prod
```

Output:

```text
apps/desktop/release/Aegisure-1.0.0-mac-arm64.dmg
```

## 6. Clean Install Test

```bash
pnpm aura:clean-mac-qa
pnpm aura:package
scripts/clean-mac-qa.sh --reset-local-state
open apps/desktop/release/Aegisure-1.0.0-mac-arm64.dmg
```

Expected:

- Aegisure opens to onboarding.
- Voice output test works through macOS `say`.
- Native push-to-talk either works or gives a precise permission/helper error.
- Overlay can be shown and accepts commands.
- License token activates locally and, when `AEGISURE_LICENSE_SERVER_URL` is set, activates the device online.
- Guardian blocks dangerous commands and secret memory.

## 7. Release Gate Commands

```bash
pnpm aura:release-checklist
pnpm aura:smoke
pnpm aura:alpha-check
pnpm aura:package
```

`pnpm aura:release-checklist` is allowed to warn on a development machine, but every warning should be cleared before a paid public release.
