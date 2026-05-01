# Packaging

AURA private alpha packaging is desktop-first and local-first.

## Targets

- Windows: NSIS installer.
- macOS: DMG.
- Linux: AppImage.

## Readiness

Before shipping a private alpha build, run:

```bash
python infra/scripts/private_alpha_check.py
```

Then run the available test suites for the current machine. If desktop tests cannot run because Node or pnpm is unavailable, record that as a release limitation.

On Windows, run the packaging smoke check:

```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/package_smoke.ps1
```

The smoke check runs private-alpha readiness first, verifies Node/pnpm availability, and runs desktop test/build/package steps when pnpm is installed.

On macOS/Linux, run:

```bash
bash infra/scripts/build_desktop.sh
```

## Alpha Guarantees

- Local profile storage remains the default.
- Risky actions still go through approval.
- Logs and audit records must be available for debugging.
- User web subscriptions are used only through user-controlled browser sessions.
- Release notes must include known limitations and rollback steps.
