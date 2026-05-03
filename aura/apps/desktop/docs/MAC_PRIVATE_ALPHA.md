# AURA Mac Private Alpha Install + Test Guide

This guide is for **private-alpha product testing on macOS**. It is not App Store guidance, and it does not assume code contribution work.

## What this build includes

- A real Electron packaging path for macOS.
- A packaged desktop app that bundles the AURA backend source inside the app resources.
- Automatic backend start/healthcheck/stop from the desktop app.
- Honest local-model readiness checks for Ollama-backed drafting.

## What this build does **not** hide

- **Mac-first private alpha**
- **Unsigned app** by default, so macOS may require manual Allow/Open steps
- **Local Python is still required**
- **Backend Python dependencies are still required**
- **Real drafting still requires local Ollama plus a pulled model**
- **Windows is not part of this private-alpha packaged flow**

## Prerequisites on the Mac

Install these before first launch:

1. **Python 3.10+**
   ```bash
   python3 --version
   ```
2. **Backend runtime dependencies**
   - If you already have the repo locally:
     ```bash
     cd aura/apps/backend
     python3 -m pip install -r requirements-private-alpha.txt
     ```
   - If you are testing from an installed `.app` without the repo:
     ```bash
     python3 -m pip install -r "/Applications/AURA.app/Contents/Resources/backend/requirements-private-alpha.txt"
     ```
3. **Optional browser/research dependency install**
   - Only needed for browser/research flows:
     ```bash
     python3 -m playwright install chromium
     ```
4. **Ollama installed and running** for real assist drafting
   ```bash
   ollama serve
   ```
5. **At least one local model pulled**, for example:
   ```bash
   ollama pull qwen2.5:3b
   ```

## Build/package commands

From the repo checkout:

```bash
cd aura/apps/desktop
npm install
npm run package:mac
```

That produces an unpacked Mac app for quick local installation/testing.

To produce distributable private-alpha artifacts:

```bash
cd aura/apps/desktop
npm install
npm run dist:mac
```

Run `dist:mac` on a Mac build machine. The unpacked `.app` path is validated in this repo environment, but DMG generation is a macOS-hosted step for private-alpha packaging.

## Output locations

After `npm run package:mac`:

- Unpacked app:
  - `aura/apps/desktop/release/mac*/AURA.app`

After `npm run dist:mac`:

- Packaged app:
  - `aura/apps/desktop/release/mac*/AURA.app`
- DMG:
  - `aura/apps/desktop/release/*.dmg`
- Zip:
  - `aura/apps/desktop/release/*.zip`

The exact `mac*` folder name depends on the build machine architecture, typically `mac-arm64` or `mac`.

## Install/open flow on macOS

### If you built `package:mac`
1. Open Finder.
2. Go to `aura/apps/desktop/release/mac*/`.
3. Drag `AURA.app` into `/Applications`.
4. Open `AURA.app`.

### If you built `dist:mac`
1. Open the generated `.dmg`.
2. Drag `AURA.app` into `/Applications`.
3. Eject the `.dmg`.
4. Open `AURA.app`.

### If macOS blocks the app because it is unsigned
1. In Finder, right-click `AURA.app`.
2. Choose **Open**.
3. Confirm **Open** again.
4. If needed, go to **System Settings → Privacy & Security** and allow the blocked app.

## What to expect on first launch

1. The desktop app opens the dashboard window.
2. AURA checks `http://127.0.0.1:8000/health`.
3. If no backend is already running, AURA attempts to start the bundled backend automatically.
4. The dashboard should show one of these honest states:
   - backend connected and healthy
   - backend launch failed because Python/dependencies are missing
   - backend launch failed because the bundled backend could not be located
5. Onboarding appears if you have not completed it before.
6. If Ollama or the selected model is missing, onboarding/model status should say so clearly and block real drafting.

## How to verify backend auto-start works

1. Quit any existing AURA backend process.
2. Open `AURA.app`.
3. Wait a few seconds.
4. In the app, confirm backend status becomes healthy/connected.
5. If it fails, confirm the app shows a clear backend failure message.
6. Quit the app and confirm the desktop-managed backend process exits.

## How to verify onboarding works

1. Launch the app on a clean profile or the first time on that Mac user.
2. Confirm onboarding opens automatically.
3. Walk through:
   - hotkey/overlay step
   - permissions/capture step
   - model step
   - starter preferences
   - first task
4. If Ollama/model is not ready, confirm onboarding says that explicitly instead of pretending drafting is available.

## How to test the hero flow like a user

1. Start Ollama:
   ```bash
   ollama serve
   ```
2. Confirm the selected model is installed:
   ```bash
   ollama list
   ```
3. Open another app and select or copy a short paragraph.
4. In AURA, use onboarding or the dashboard and run:
   - `Summarize this`
5. Confirm AURA:
   - captures context
   - generates a real draft
   - asks for approval
   - lets you approve/copy/paste back

## Known limitations in this private-alpha pass

- macOS-focused only
- unsigned app by default
- no notarization
- no embedded Python runtime yet
- backend depends on local Python packages
- real assist drafting depends on local Ollama and a pulled local model
- browser/research flows may require `playwright install chromium`
