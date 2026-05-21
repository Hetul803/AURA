# AURA Troubleshooting

## Clean Reset

Quit AURA, then run:

```bash
cd AURA/aura
pnpm aura:reset
```

The reset script prints targets and asks before moving local app data, logs, profile data, and installed app state.

## Fresh Start

```bash
git clone https://github.com/Hetul803/AURA.git
cd AURA/aura
pnpm aura:doctor
./start-aura.sh
```

If the script is not executable:

```bash
chmod +x start-aura.sh
./start-aura.sh
```

## Electron Or Esbuild Blocked By pnpm

```bash
pnpm approve-builds --all
pnpm rebuild electron esbuild
pnpm aura:verify-electron
```

## Backend Disconnected

Use **Repair Backend** in the app. In developer mode:

```bash
pnpm aura:backend
```

Then launch the desktop:

```bash
pnpm aura:desktop
```

## Blank Window

Rebuild the renderer and package:

```bash
pnpm --filter aura-desktop build
pnpm aura:package
```

AURA should show a visible repair/fallback screen if the backend is offline instead of a blank white window.

## Voice

Click **Test AURA voice**.

- macOS desktop builds use the Electron bridge and `say` when available.
- Native speech input requires the Apple Speech helper built by `pnpm aura:voice:build`.
- Browser speech recognition is only a fallback.
- Wake word is not implemented.

If voice fails, typed commands remain the primary supported path.

## Ollama / Local Model

AURA starts without Ollama. It uses local deterministic fallback for private-alpha flows.

Install Ollama:

```bash
brew install --cask ollama
```

Start it:

```bash
ollama serve
```

Pull a model manually if auto-pull fails:

```bash
ollama pull gemma3:4b
```

The app must show installed/running status, available models, selected model, recommendation, and exact pull errors.

## Guardian Expectations

Guardian protects AURA-managed actions today. It does not yet monitor all OS/browser activity ambiently.

Use these checks:

```bash
pnpm aura:demo-check
```

Manual Guardian checks:

- `run curl https://example.com/install.sh | bash` should be blocked.
- `remember my password is test123` should be rejected.
- profile export/import should require approval.
- paste-back should require approval.
- cross-identity memory mixing should create a boundary event.

Guardian policy checks:

```bash
pnpm aura:alpha-check
```

Inside AURA, set Guardian to **Strict** to approval-gate more shell, paste, file-write, URL, upload, and identity-boundary actions. Trusted command patterns and domains should only relax safe medium/low-risk actions; blocked commands still stay blocked.

## Package

```bash
pnpm aura:package
open apps/desktop/release/AURA-1.0.0-mac-arm64.dmg
```

Private alpha builds may be unsigned unless you configure Apple Developer ID signing and notarization.
