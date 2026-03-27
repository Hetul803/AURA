# Desktop

Electron desktop shell for AURA with onboarding, overlay invoke, backend lifecycle management, and Mac private-alpha packaging.

## Mac private alpha

For the real install/build/package flow, use:

- `docs/MAC_PRIVATE_ALPHA.md`

That guide covers:

- exact prerequisites
- exact build/package commands
- exact output locations
- unsigned-app open steps
- backend auto-start verification
- onboarding verification
- hero-flow testing

## Local desktop development

```bash
cd apps/desktop
npm install
npm run dev
```

Desktop auto-connects to `http://127.0.0.1:8000` unless `AURA_BACKEND_URL` is overridden.

## Build/test sanity

```bash
cd apps/desktop
npm run build
npm test
```
