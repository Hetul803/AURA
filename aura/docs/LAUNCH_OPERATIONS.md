# Launch Operations

This is the operator checklist for giving AURA to the first 10 real private-alpha users.

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
AURA_WEB_DB_PATH=/var/lib/aura/private-alpha-store.json
AURA_VENDOR_PRIVATE_KEY=...
AURA_VENDOR_PUBLIC_KEY=...
AURA_ADMIN_TOKEN=...
```

Routes:

- `POST /api/checkout/create`
- `POST /api/stripe/webhook`
- `POST /api/devices/activate`
- `POST /api/devices/revoke`
- `POST /api/crash-reports`

For the first 10 users, the durable JSON store is acceptable on one server with backups. Before broad launch, replace `AlphaStore` with Postgres.

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
apps/desktop/release/AURA-1.0.0-mac-arm64.dmg
```

## 6. Clean Install Test

```bash
rm -rf "/Applications/AURA.app"
rm -rf "$HOME/Library/Application Support/aura-desktop"
rm -rf "$HOME/Library/Logs/aura-desktop"
rm -rf "$HOME/.aura"
open apps/desktop/release/AURA-1.0.0-mac-arm64.dmg
```

Expected:

- AURA opens to onboarding.
- Voice output test works through macOS `say`.
- Native push-to-talk either works or gives a precise permission/helper error.
- Overlay can be shown and accepts commands.
- License token activates locally and, when `AURA_LICENSE_SERVER_URL` is set, activates the device online.
- Guardian blocks dangerous commands and secret memory.

