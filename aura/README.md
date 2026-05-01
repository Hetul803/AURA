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

## Known intentional stubs
- Voice transcription
- Final purchase/checkout completion (confirmation-gated)
