# AURA Private Alpha Launch Readiness

This repo is now set up for a serious private alpha, not public App Store distribution yet.

## Brand Rename

AURA can be renamed before packaging:

```bash
pnpm aura:brand -- --name="Your Product Name" --company="Your Company" --app-id="com.yourcompany.yourproduct"
pnpm aura:package
```

This updates:

- `config/brand.json`
- `apps/desktop/electron-builder.yml` product name
- macOS artifact name
- bundle app id

For public launch, also replace the app icon, legal links, website copy, code-signing identity, notarization settings, and update server metadata.

## Signed Licenses

AURA supports offline-verifiable Ed25519 license tokens. The app only ships the public key. Never ship the private key.

Generate vendor keys:

```bash
python scripts/generate-license-key.py --key-dir ~/AURA_VENDOR_KEYS
```

Generate a private-alpha license:

```bash
python scripts/generate-license-key.py \
  --key-dir ~/AURA_VENDOR_KEYS \
  --email alpha-user@example.com \
  --tier private_alpha \
  --expires-at 2026-12-31T23:59:59Z
```

Set the public key for local testing before starting/building:

```bash
export AURA_LICENSE_PUBLIC_KEY="$(cat ~/AURA_VENDOR_KEYS/vendor_public.pem)"
```

Then paste the generated token into Settings -> License.

For paid launch, the website should issue signed tokens after checkout. The app should verify them locally and later sync device activations to a server.

## Cryptographic Identity

Each local identity gets an Ed25519 keypair:

- public key and fingerprint are visible in the UI;
- private key is encrypted at rest using a local master key in the profile secrets folder;
- audit payloads for important AURA actions include identity signatures;
- hardware-bound identity sync is planned for the license server and is not claimed yet.

This prevents identity from being just a database number, but it is not a full anti-copy DRM system. If someone copies the entire local profile and master key, they can copy that local identity. Production hardening should bind license activation to devices and offer user-controlled backup/recovery.

## Encrypted Memory

Typed Memory values are encrypted at rest before being written to SQLite. The UI and API decrypt them for the local user.

What is protected:

- memory values;
- identity private keys;
- secret-like memory writes are rejected before storage;
- exported/imported profiles require Guardian approval.

What is not solved yet:

- full database encryption;
- cloud sync;
- hardware-backed keys;
- multi-user recovery.

## 10-User Private Alpha Checklist

Before giving the app to 10 users:

1. Choose final product name with `pnpm aura:brand`.
2. Add a real icon.
3. Build and test the signed-license flow.
4. Code-sign and notarize the macOS app.
5. Prepare a clean download page with reset/troubleshooting docs.
6. Test fresh install on at least two Macs.
7. Verify voice output, overlay, local model setup, Guardian blocking, memory persistence, identity switching, and clone/coding-job flows.
8. Collect logs manually from users; automatic crash/error reporting is not implemented yet.

## Reality Boundary

AURA is much closer to private-alpha readiness, but not yet a fully public production product. The biggest remaining public-launch gaps are:

- code signing and notarization;
- real account server;
- license device activation/revocation;
- robust native speech-to-text beyond browser Web Speech fallback;
- OS-wide Guardian monitoring outside AURA-managed actions;
- full database encryption and backup/recovery;
- crash reporting and auto-update.
## Current Private-Alpha Launch Gate

Run:

```bash
pnpm aura:alpha-check
pnpm aura:smoke
pnpm aura:package
```

These checks cover local machine doctor diagnostics, private-alpha documentation/packaging metadata, Guardian/Memory/Identity product tests, desktop renderer tests/build, Electron verification, and DMG creation.

Before a 10-user alpha, verify manually:

- onboarding reset works on a clean Mac;
- overlay can be shown and moved;
- voice test works or reports the exact limitation;
- Guardian strict mode and blocked commands appear in the Watchtower;
- memory survives restart and affects a draft;
- identity switch changes memory scope and ledger entries;
- GitHub clone, draft reply, coding job, open URL/app, workspace note, and prepare-work-session flows are testable.
