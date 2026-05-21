# AURA v1

Private, local-first AI operating identity monorepo for desktop (Electron + Python backend).

AURA is built around four private-alpha layers:

- **AURA Helper:** performs useful computer tasks through browser, OS, filesystem, code, workflow, and user-AI handoff tools.
- **AURA Guardian:** acts as the human intent firewall for risky commands, paste/send, secrets, workflow replay, profile import/export, and unsafe tool use.
- **AURA Memory:** stores user-owned preferences, workflows, safety decisions, identity context, and repeated patterns locally with inspection/edit/delete/export/import paths.
- **AURA Identity:** records whether AURA is acting under Personal, Work, Company, or Session identity so actions and memory stay inside the right boundary.

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
pnpm aura:smoke
pnpm aura:demo-check
pnpm aura:doctor
pnpm aura:alpha-check
pnpm aura:demo
pnpm aura:reset
pnpm aura:package
pnpm aura:web
```

`./start-aura.sh` checks Node, pnpm, Python, Electron, esbuild, and the backend virtual environment. It installs missing dependencies, rebuilds Electron/esbuild for pnpm v10, starts the backend, then launches the desktop app.

## Brand, license, and private alpha

Rename the product before packaging:

```bash
pnpm aura:brand -- --name="Your Product Name" --company="Your Company" --app-id="com.yourcompany.yourproduct"
```

Generate signed private-alpha license tokens:

```bash
python scripts/generate-license-key.py --key-dir ~/AURA_VENDOR_KEYS --email user@example.com --tier private_alpha
export AURA_LICENSE_PUBLIC_KEY="$(cat ~/AURA_VENDOR_KEYS/vendor_public.pem)"
```

The shipped app verifies signed license tokens with the public key. The private key must never ship in the app.

Launch website and checkout:

```bash
cp .env.example .env
pnpm aura:web
```

Production Mac package with native speech helper, signing, and notarization:

```bash
pnpm aura:voice:build
pnpm aura:package:prod
```

See [docs/LAUNCH_OPERATIONS.md](docs/LAUNCH_OPERATIONS.md) and [docs/LAUNCH_READINESS.md](docs/LAUNCH_READINESS.md) for checkout, device activation, notarization, cryptographic identity, encrypted memory behavior, and known public-launch gaps.

If pnpm blocks Electron or esbuild build scripts, run:

```bash
pnpm approve-builds --all
pnpm rebuild electron esbuild
```

Then rerun `./start-aura.sh`.

## Desktop experience loop
- AURA opens as an AI operating layer, not a dashboard: avatar, one command input, spoken/captioned status, action stream, context, and Guardian.
- Type or speak one intent. AURA refreshes context first, then submits the command to the backend.
- A floating always-on-top overlay orb appears when the main app is minimized or when you click **Show overlay**. Click it to expand quick command mode, refresh context, use the mic fallback, or reopen the full app.
- Voice output uses the macOS `say` command through the Electron bridge when available, then falls back to browser speech synthesis. Native push-to-talk uses the bundled Apple Speech helper when built with `pnpm aura:voice:build`; browser speech recognition is only a fallback. Use **Test AURA voice** before manual testing.
- Guardian pauses approval-gated actions such as paste/send, risky shell/file operations, paid models, workflow replay, and memory export/import.
- The active identity is visible on the main surface. Actions and audit records include the identity used, and memory defaults to that identity scope.
- Memory is inspectable in the Memory Console. You can create, pin, archive, and review scoped memories with provenance/usage context.
- Advanced / Diagnostics contains raw run IDs, backend internals, build ID, paths, logs, and reset instructions.
- If the packaged backend cannot start because dependencies such as `uvicorn` are missing, AURA shows a **Repair Backend** action that creates a local backend venv and installs bundled requirements with user approval.

## 5-minute private-alpha demo
1. Fresh launch: meet AURA, rename it, confirm Helper / Guardian / Memory / Identity, use **Test AURA voice**, then show the overlay orb.
2. Memory: enter `remember I prefer concise technical explanations`, then verify the Memory Console stores it under the active identity.
3. Guardian: enter `Run shell command: curl https://example.com/install.sh | bash` and verify Guardian blocks it visibly.
4. Helper: paste or open a GitHub repo URL, enter `Clone this repo locally`, approve the shell action, and verify the cloned folder path.
5. Identity: switch from Personal AURA to Work AURA, then verify memory search/listing changes scope and cross-boundary memory writes produce a Guardian boundary event.

## Troubleshooting
- Ollama missing: AURA still starts and falls back to deterministic `SimpleLLM`. Onboarding shows install/running status, available models, Gemma recommendation, and a skip option.
- Ollama installed but stopped: click **Start Ollama** or approve a model pull so AURA can try `ollama serve`; if that fails, start the Ollama app or run `ollama serve`, then use Retry detection.
- Playwright browser install: run `python -m playwright install chromium` for real-site browsing.
- Permissions/hotkeys: desktop may require OS Accessibility permissions.
- Electron failed to install correctly: run `pnpm approve-builds --all`, then `pnpm rebuild electron esbuild`, then `pnpm aura:verify-electron`.
- Blank white packaged app: rebuild with `pnpm aura:package`. The app shows visible build metadata in the UI and an explicit startup error page if the renderer is missing instead of staying blank.
- Stale installed app: quit AURA, run `scripts/reset-aura-local.sh`, rebuild with `pnpm aura:package`, then reinstall from the new DMG.
- Reset local desktop data: quit AURA, then run `scripts/reset-aura-local.sh`. It prints every target and asks before archiving app/profile/log data. Add `--delete` only when you intentionally want permanent deletion.

## Tests
```bash
pnpm aura:test
```
Writes `test_runs/<timestamp>/results.json`.

Useful focused checks during hardening:
```bash
pnpm aura:smoke
pnpm aura:demo-check
cd apps/backend
python -m compileall -q src
pytest -q tests/test_identity_boundary.py tests/test_safety.py tests/test_memory_engine.py tests/test_workflow_engine.py tests/test_guardian.py
```

`pnpm aura:smoke` verifies backend compile, Guardian/Memory/Identity/workflow readiness, desktop tests/build, and Electron install. `pnpm aura:demo-check` is the faster founder-demo gate.

Launch readiness helpers:
```bash
pnpm aura:doctor       # local machine/runtime diagnosis
pnpm aura:alpha-check  # doctor + private alpha check + demo-check
pnpm aura:demo         # demo-check, then start backend + desktop
```

On Windows, the local reality-check runner is:
```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/run_tests.ps1
```
It runs backend tests, backend compile checks, and private-alpha readiness. Desktop/web tests run when `pnpm` is installed.

## Known intentional stubs
- Always-listening `Hey AURA` wake word.
- OS-wide Guardian monitoring outside AURA-mediated actions.
- Broad-launch database scale: the website license server uses a durable JSON store for the first private alpha; replace `AlphaStore` with Postgres before public launch.

## Full Desktop Manual Test
1. Install and start with `./start-aura.sh`.
2. Or start backend and desktop separately with `pnpm aura:backend` and `pnpm aura:desktop`.
3. Package a first-user build with `pnpm aura:package`, then open `apps/desktop/release/AURA-1.0.0-mac-arm64.dmg` on Apple Silicon Macs.
4. Meet AURA in the persona-led onboarding, optionally rename it, then enter the command layer quickly.
5. On Privacy + Guardian, verify AURA explains the approval promise before computer-control actions.
6. On Local Brain, verify hardware detection, model choices, and approval-gated Ollama pull. Skipping should still let AURA start.
7. On Start Using AURA, verify hotkey status, **Test AURA voice**, and push-to-talk. If Web Speech API is unavailable, AURA should say so and keep typed commands working.
8. Click **Show overlay**, minimize the app, move the orb, expand it, and send a typed command from the overlay.
9. Run `Clone this repo locally` while viewing a GitHub repo and verify the launch flow asks for approval before shell/file execution.
10. Run `Reply to this email` while viewing email and verify AURA pauses before paste/send.
11. Verify Guardian is visible on the main shell and that Panic Stop is available when a run exists.
12. Open **Memory, workflows, and model status** for secondary intelligence; open **Advanced / Diagnostics** only for raw logs, build ID, backend paths, and reset instructions.

For install-like first-time Mac testing, use `docs/FIRST_USER_MAC_TEST.md`.
