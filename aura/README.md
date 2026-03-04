# AURA v1

Local-first AI computer operator monorepo for desktop (Electron + Python backend).

## Quick start
```bash
pnpm -w install
cd apps/backend && pip install -e .
pnpm -w dev
```
Desktop UI (renderer tests) lives in `apps/desktop`. In full desktop mode, Electron hosts this renderer and talks to backend HTTP/SSE.

## 3 demos that always work
1. `search ai operator design and give me key points`
2. `open gmail` then choose clarifications once, then `summarize unread emails` (real Gmail may require login)
3. `find flights from SFO to JFK on 2026-07-01 return 2026-07-10` then open best option as dry-run (no booking)

## Troubleshooting
- Ollama missing: backend auto-falls back to deterministic `SimpleLLM`.
- Playwright browser install: run `python -m playwright install chromium` for real-site browsing.
- Permissions/hotkeys: global hotkey may require OS accessibility permissions.

## Tests
```bash
bash infra/scripts/run_tests.sh
```
Writes `test_runs/<timestamp>/results.json`.

## Known intentional stubs
- Voice transcription (UI and backend signal stubbed transcription)
- Final purchase/checkout completion is confirmation-gated and not auto-finalized
