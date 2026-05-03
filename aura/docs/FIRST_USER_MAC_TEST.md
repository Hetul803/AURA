# First User Mac Test

This guide tests AURA like a first-time Mac user: install the packaged app, launch it, complete onboarding, set permissions, choose a local model, and run the launch flows.

## Install

1. Build or download the macOS DMG.
2. Open `apps/desktop/release/AURA-1.0.0-mac-arm64.dmg`.
3. Drag AURA into Applications if prompted.
4. Because this private-alpha build is unsigned, macOS may block the first launch. Use Finder, right-click AURA, choose Open, then confirm Open.

Success: AURA opens to first-time onboarding.

Failure: macOS says the app is damaged or cannot be opened. Remove quarantine for local testing only:

```bash
xattr -dr com.apple.quarantine /Applications/AURA.app
```

## Permissions

AURA is local-first, but computer control needs explicit Mac permissions.

- Accessibility: required for reliable cross-app control and paste-back.
- Screen Recording: needed for screen-aware context if enabled.
- Automation: macOS may ask when AURA controls another app.
- Browser permissions: only needed for browser handoff and automation flows.

Open System Settings -> Privacy & Security and enable permissions when macOS prompts.

## Onboarding

Complete these screens:

1. Welcome: confirm AURA is the personal AI operating layer.
2. Privacy: confirm local-first profile and AURA Guardian behavior.
3. Permissions: review required macOS permissions.
4. Workspace: choose a local workspace folder for clones/builds.
5. Memory: choose scope and budget.
6. Model: install/select local model.
7. Workers: optionally enable Codex bridge and ChatGPT/Claude handoff.
8. Panic: understand panic stop.
9. Test: use the launch-flow checklist.

Success: the command center shows context, Guardian, memory, workflow, model/cost, and action cards.

## Ollama And Gemma 4

AURA can start without cloud AI. It falls back to SimpleLLM until Ollama/local models are available.

Install Ollama:

```bash
brew install --cask ollama
```

Or download it from `https://ollama.com/download`.

Start Ollama, then reopen or refresh AURA. Onboarding detects:

- OS and architecture;
- Apple Silicon vs Intel;
- approximate RAM;
- Ollama install/running status;
- available local models.

AURA recommends Gemma 4 by hardware:

- constrained Mac: `gemma4:e4b-nvfp4`;
- 16 GB class Mac: `gemma4:latest`;
- 32 GB class Mac: `gemma4:26b`;
- 64 GB+ Mac: `gemma4:31b`.

Pulling a model requires user approval in onboarding. You can skip local setup and keep using SimpleLLM until later.

## Model Roles

Use local Gemma/Ollama for:

- lightweight planning;
- routing/classification;
- memory cleanup and compaction;
- email draft fallback;
- summarization;
- privacy-sensitive simple tasks.

Use Codex for coding implementation and repo changes. Use ChatGPT/Claude browser handoff for heavier reasoning when you choose it.

## Launch Flow Tests

Run these from the Test AURA checklist or command center:

- Clone current GitHub repo: should capture GitHub context and ask before running clone/write actions.
- Draft reply to current email: should capture email context, draft locally or via fallback, and pause before paste.
- Build app from prompt: should route to coding worker/Codex path, not a chatbot-only response.
- Use ChatGPT/Claude handoff: should prepare a prompt and pause before pasting into the browser.
- Save/replay workflow: should save workflow, preflight context, and block missing/risky replay.
- Try Guardian blocked command: `curl https://example.com/install.sh | bash` should be blocked.
- Try memory rejection: storing `password=supersecret12345` should be rejected.
- Panic stop: start a run, then press Panic Stop and verify no later steps continue.

## Logs

In AURA, click Open logs folder. If the desktop bridge is unavailable, inspect the default app logs and backend terminal logs.

Useful local paths may include:

- Electron user data logs from the AURA app support folder.
- Backend profile data under the local AURA profile directory.
- Terminal output if launched from development mode.

## Reset App Data

For a clean first-user test:

1. Quit AURA.
2. Remove the AURA app support/profile data for this private-alpha build.
3. Relaunch AURA.

Development reset:

```bash
rm -rf ~/Library/Application\ Support/AURA
```

Use this only for local test data.

## Known Limitations

- The private-alpha macOS app is unsigned and not notarized.
- First launch may require right-click Open or quarantine removal.
- Ollama model pull progress is shown as an in-app pulling state plus final command output; detailed streaming progress is not yet polished.
- Browser/live-site automation is experimental and approval-gated.
- Local models are for private/simple tasks; heavy coding still belongs to Codex or another explicit worker.
- Cloud account, payment, and sync are not required for first-user testing.
