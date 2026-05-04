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

If your shell says the script is not executable after a zip/manual copy, fix the bit once:

```bash
chmod +x start-aura.sh
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

## Desktop experience loop
- AURA opens as an AI operating layer, not a dashboard: avatar, one command input, spoken/captioned status, action stream, context, and Guardian.
- Type or speak one intent. AURA refreshes context first, then submits the command to the backend.
- Guardian pauses approval-gated actions such as paste/send, risky shell/file operations, paid models, workflow replay, and memory export/import.
- Advanced / Diagnostics contains raw run IDs, backend internals, build ID, paths, logs, and reset instructions.
- If the packaged backend cannot start because dependencies such as `uvicorn` are missing, AURA shows a **Repair Backend** action that creates a local backend venv and installs bundled requirements with user approval.

## 3 best demo commands
1. `search ai operator design and give me key points`
2. `open gmail` then `summarize unread emails` (may require manual login + Continue)
3. `find flights from SFO to JFK on 2026-07-01 return 2026-07-10`

## Troubleshooting
- Ollama missing: AURA still starts and falls back to deterministic `SimpleLLM`. Onboarding shows install/running status, available models, Gemma recommendation, and a skip option.
- Ollama installed but stopped: start the Ollama app or run `ollama serve`, then use Retry detection in onboarding.
- Playwright browser install: run `python -m playwright install chromium` for real-site browsing.
- Permissions/hotkeys: desktop may require OS Accessibility permissions.
- Electron failed to install correctly: run `pnpm approve-builds --all`, then `pnpm rebuild electron esbuild`, then `pnpm aura:verify-electron`.
- Blank white packaged app: rebuild with `pnpm aura:package`. The app shows visible build metadata in the UI and an explicit startup error page if the renderer is missing instead of staying blank.
- Stale installed app: quit AURA, run `scripts/reset-aura-local.sh`, rebuild with `pnpm aura:package`, then reinstall from the new DMG.
- Reset local desktop data: quit AURA, then run `scripts/reset-aura-local.sh`. It prints every target and asks before deleting app/profile/log data.

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
- Always-listening `Hey AURA` wake word. Push-to-talk uses Web Speech API when the Electron runtime exposes it; typed input remains the fallback.
- Final purchase/checkout completion (confirmation-gated)

## Full Desktop Manual Test
1. Install and start with `./start-aura.sh`.
2. Or start backend and desktop separately with `pnpm aura:backend` and `pnpm aura:desktop`.
3. Package a first-user build with `pnpm aura:package`, then open `apps/desktop/release/AURA-1.0.0-mac-arm64.dmg` on Apple Silicon Macs.
4. Meet AURA in the persona-led onboarding, optionally rename it, then enter the command layer.
5. On Local Brain, verify hardware detection, model choices, and approval-gated Ollama pull. Skipping should still let AURA start.
6. On Finish, verify hotkey status, speech output, and push-to-talk. If Web Speech API is unavailable, AURA should say so and keep typed commands working.
7. Run `Clone this repo locally` while viewing a GitHub repo and verify the launch flow asks for approval before shell/file execution.
8. Run `Reply to this email` while viewing email and verify AURA pauses before paste/send.
9. Verify Guardian is visible on the main shell and that Panic Stop is available when a run exists.
10. Open **Memory, workflows, and model status** for secondary intelligence; open **Advanced / Diagnostics** only for raw logs, build ID, backend paths, and reset instructions.

For install-like first-time Mac testing, use `docs/FIRST_USER_MAC_TEST.md`.
