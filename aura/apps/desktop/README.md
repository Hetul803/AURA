# Desktop

Electron GUI overlay for AURA with live backend connection state, SSE run timeline, panic stop, and resume UX.

## Run (macOS/Windows)
1. Start backend+web from repo root:
   ```bash
   pnpm -w dev
   ```
2. In another terminal:
   ```bash
   cd apps/desktop
   pnpm install
   pnpm dev
   ```

Desktop auto-connects to `http://localhost:8000` (override with `AURA_BACKEND_URL`).

## What to verify in the desktop app
- Onboarding opens on first run and saves local profile settings.
- The Current Context card shows what AURA sees.
- The Run panel shows approvals as decision cards, not chat bubbles.
- The Guardian panel shows protected status, risk explanations, and panic stop.
- The Memory panel shows scoped memory and compaction.
- The Workflow panel shows saved workflows, suggestions, and replay.
- The System panel shows tools, device adapters, and local profile state.

## Launch flows to test
- `Clone this repo locally`
- `Summarize this`
- `Reply to this email`
- `Build me a SaaS landing page for this idea`
- `Use my ChatGPT subscription to write a reply to this email`
- Run a saved workflow from the Workflow panel.

## Troubleshooting
- If status shows **Disconnected**, verify backend `/health` at `http://localhost:8000/health`.
- On macOS, grant Accessibility permissions if hotkeys/tray interactions are restricted.
- On Windows, run terminal as standard user first; elevate only if OS automation permissions require it.
- If Electron fails to load renderer, ensure port `5173` is not blocked.

## Test + build sanity
```bash
pnpm test
pnpm build
```
