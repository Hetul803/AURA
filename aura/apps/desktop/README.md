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
