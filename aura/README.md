# AURA v1

Local-first AI computer operator monorepo for desktop (Electron + Python backend).

## Source of truth

Read [docs/AURA_VISION_AND_BUILD_CONSTITUTION.md](docs/AURA_VISION_AND_BUILD_CONSTITUTION.md) before planning or implementing any AURA task. It defines the long-term product vision, platform primitives, safety rules, memory boundaries, cost philosophy, cross-device future, enterprise direction, and required development workflow.

## Quick start
```bash
pnpm -w install
cd apps/backend && pip install -e .
cd ../..
pnpm -w dev
```
In another terminal:
```bash
cd apps/desktop
pnpm dev
```

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

## Tests
```bash
bash infra/scripts/run_tests.sh
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
1. Install dependencies with `pnpm -w install` and `cd apps/backend && pip install -e .`.
2. Start backend/web with `pnpm -w dev`.
3. Start desktop with `cd apps/desktop && pnpm dev`.
4. Complete onboarding and save local profile settings.
5. Run `Summarize this` with selected or copied text and verify approval is required before paste-back.
6. Run `Clone this repo locally` while viewing a GitHub repo and verify the launch flow is visible and safe.
7. Open the Guardian panel and verify risky actions, redaction, and panic stop are visible.
8. Open Memory and Workflow panels and verify memory compaction and workflow replay are testable.
