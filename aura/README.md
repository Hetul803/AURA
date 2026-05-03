# AURA v1

Local-first AI computer operator monorepo for desktop (Electron + Python backend).

## Source of truth

Read [docs/AURA_VISION_AND_BUILD_CONSTITUTION.md](docs/AURA_VISION_AND_BUILD_CONSTITUTION.md) before planning or implementing any AURA task. It defines the long-term product vision, platform primitives, safety rules, memory boundaries, cost philosophy, cross-device future, enterprise direction, and required development workflow.

## Quick start

Fresh clone developer start:

```bash
git clone https://github.com/Hetul803/AURA.git
cd AURA/aura
./start-aura.sh
```

Equivalent pnpm commands from `AURA/aura`:

```bash
pnpm aura:start
pnpm aura:install
pnpm aura:backend
pnpm aura:desktop
pnpm aura:test
pnpm aura:package
```

`./start-aura.sh` checks Node, pnpm, Python, Electron, esbuild, and the backend virtual environment. It installs missing dependencies, rebuilds Electron/esbuild for pnpm v10, starts the backend, then launches the desktop app.

If pnpm blocks Electron or esbuild build scripts, run:

```bash
pnpm approve-builds --all
pnpm rebuild electron esbuild
```

Then rerun `./start-aura.sh`.

## Desktop demo loop
- Desktop shows backend status (Connected/Disconnected + retry)
- Enter command -> receives `run_id` -> subscribes to `/events/stream/{run_id}`
- Action timeline updates live
- AURA Guardian shows protection status, risk explanations, and redacted safety events
- Panic Stop calls `/panic/{run_id}`
- If blocked with manual step, click **Continue** to call `/runs/{run_id}/resume`

## 3 best demo commands
1. `search ai operator design and give me key points`
2. `open gmail` then `summarize unread emails` (may require manual login + Continue)
3. `find flights from SFO to JFK on 2026-07-01 return 2026-07-10`

## Troubleshooting
- Ollama missing: backend auto-falls back to deterministic `SimpleLLM`.
- Playwright browser install: run `python -m playwright install chromium` for real-site browsing.
- Permissions/hotkeys: desktop may require OS Accessibility permissions.
- Electron failed to install correctly: run `pnpm approve-builds --all`, then `pnpm rebuild electron esbuild`, then `pnpm aura:verify-electron`.
- Blank white packaged app: rebuild with `pnpm aura:package`. The app now loads an explicit startup error page if the renderer is missing instead of staying blank.
- Reset local desktop data: quit AURA, then run `rm -rf ~/Library/Application\ Support/AURA`.

## Tests
```bash
pnpm aura:test
```
Writes `test_runs/<timestamp>/results.json`.

Useful focused checks during hardening:
```bash
cd apps/backend
python -m compileall -q src
pytest -q tests/test_safety.py tests/test_memory_engine.py tests/test_workflow_engine.py tests/test_guardian.py
```

On Windows, the local reality-check runner is:
```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/run_tests.ps1
```
It runs backend tests, backend compile checks, and private-alpha readiness. Desktop/web tests run when `pnpm` is installed.

## Known intentional stubs
- Voice transcription
- Final purchase/checkout completion (confirmation-gated)

## Full Desktop Manual Test
1. Install and start with `./start-aura.sh`.
2. Or start backend and desktop separately with `pnpm aura:backend` and `pnpm aura:desktop`.
3. Package a first-user build with `pnpm aura:package`, then open `apps/desktop/release/AURA-1.0.0-mac-arm64.dmg` on Apple Silicon Macs.
4. Complete onboarding and save local profile settings.
5. Run `Summarize this` with selected or copied text and verify approval is required before paste-back.
6. Run `Clone this repo locally` while viewing a GitHub repo and verify the launch flow is visible and safe.
7. Open the Guardian panel and verify risky actions, redaction, and panic stop are visible.
8. Open Memory and Workflow panels and verify memory compaction and workflow replay are testable.

For install-like first-time Mac testing, use `docs/FIRST_USER_MAC_TEST.md`.
