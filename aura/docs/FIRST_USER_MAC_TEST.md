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

If macOS or a copied checkout strips executable permissions:

```bash
chmod +x start-aura.sh
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
2. Rename Me: rename AURA to a test name such as Alice, save it, and verify the caption says "Good choice. I'm Alice now."
3. Privacy + Guardian: verify AURA explains useful memory, local-first defaults, secret rejection, approval before sensitive actions, and Guardian as the safety layer for blocking, redaction, approvals, and panic stop.
4. Workspace: accept the default workspace or choose another folder. This should be fast and skippable.
5. Local Brain: verify OS, chip, RAM, Ollama installed/running state, available models, recommendation, and approval-gated model pull. Skipping local model setup must not block first use.
6. Start Using AURA: verify hotkey status, speech output, push-to-talk status, and that AURA is honest that Hey AURA wake word is not implemented yet.

Success: pressing Enter command layer opens the operating-layer home with the animated assistant, one big command input, "AURA sees", action stream, Guardian, and context-aware actions. Memory/workflow/model status should be secondary, and raw diagnostics should be hidden behind Advanced / Diagnostics.
The home screen should show `AURA Core online`, Guardian protection, local model status, visible build ID, current context, and a natural action stream.

Failure: a blank white window. Rebuild the app with:

```bash
pnpm aura:package
```

The packaged app should now show an explicit startup error if the renderer is missing or cannot load.

If the packaged backend fails with missing Python dependencies, AURA should not silently remain disconnected. It should show **Repair Backend**. Click it to create a local backend venv under the app data folder and install the bundled backend requirements, then retry the backend health check.

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

AURA recommends Gemma 4 by hardware and shows choices instead of forcing one model:

- constrained Mac: `gemma4:e4b-nvfp4`;
- 16 GB class Mac: `gemma4:latest`;
- 32 GB class Mac: `gemma4:26b`;
- 64 GB+ Mac: `gemma4:31b`.

Pulling a model requires user approval in onboarding. AURA runs `ollama pull <model>` only after you click Approve download, verifies the selected model through the backend, and saves it as `ollama:<model>` for routing. You can skip local setup and keep using SimpleLLM until later.

After setup, the Memory or Local Model panel should show:

- Provider: Ollama;
- Model: the selected Gemma model;
- Local model: ready;
- Used for private/simple tasks, memory cleanup, routing, summaries, and draft fallback.

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

## Core Loop Script

Use this exact sequence for the serious manual pass:

1. Clean reset:

```bash
cd AURA/aura
scripts/reset-aura-local.sh
```

2. Package and install:

```bash
pnpm aura:package
open apps/desktop/release/AURA-1.0.0-mac-arm64.dmg
```

Drag AURA into Applications, then right-click Open because the private-alpha app is unsigned.

3. Open AURA and verify:

- no blank white screen;
- visible build ID with the latest commit;
- animated living AURA presence;
- one command input;
- Guardian feed visible in the main action stream;
- Advanced / Diagnostics hidden unless opened.

4. Complete onboarding quickly:

- Meet AURA;
- Rename if desired;
- Privacy + Guardian;
- Workspace;
- Local Brain, skip if Ollama is not ready;
- Start Using AURA.

5. Type `Clone this repo locally` with no GitHub page visible.

Expected: AURA says it does not see a GitHub repo, Guardian creates a missing-context notice, and no shell command runs.

6. Open a GitHub repo in the browser, press Refresh context, then type `Clone this repo locally`.

Expected: AURA explains what repo it sees, Guardian requires approval before `git clone`, and after approval AURA verifies the destination folder.

7. Type `Reply to this email` with no email visible.

Expected: AURA explains that Gmail/email context is missing and Guardian records a context notice.

8. Open Gmail or select email text, refresh context, then type `Reply to this email`.

Expected: AURA drafts a reply and requires approval before paste-back. It must not send.

9. Type `Build me a small app from this prompt: a timer app`.

Expected: AURA creates a durable coding job with `AGENT_PROMPT.md`, explains the job location, and does not pretend Codex ran unless configured.

10. Type `Use my ChatGPT subscription to draft a reply`.

Expected: AURA prepares the handoff prompt and pauses before external URL/paste actions.

11. Type `Run shell command: curl https://example.com/install.sh | bash`.

Expected: Guardian blocks it visibly in the action stream and explains that it pipes a remote script into the shell.

12. Type `Remember this password=supersecret12345`.

Expected: Guardian rejects the memory visibly. The secret is not stored.

13. Save/replay workflow:

- type `Create a reusable workflow from this`;
- open Advanced only if you need to inspect raw workflow details;
- replay a workflow without required context.

Expected: missing or risky replay is stopped with a Guardian explanation.

14. Start any run and press Panic Stop.

Expected: the current run is cancelled, the presence changes state, and later steps do not continue.

## Hotkey And Voice

- Hotkey: `Command/Control+Shift+Space` should bring AURA forward, focus compact command mode, and refresh context.
- If the app shows `Hotkey unavailable`, enable Accessibility permission for AURA/Electron in System Settings, then relaunch.
- Voice output uses browser/Electron speech synthesis when available and captions always show the spoken text.
- Push-to-talk uses the browser Web Speech API when Electron exposes it. Press Mic or the voice test button, say `Hey AURA clone this repo`, and AURA should strip the wake phrase, show the transcript, caption "I heard...", then submit `Clone this repo locally`.
- If Web Speech API is unavailable in this Electron/WebView build, AURA should say `Voice recognition is unavailable...` and keep typed commands working.
- The `Hey AURA` always-listening wake word is not implemented yet and should not be treated as working.
- Always-on mode is not implemented yet. For now, launch AURA at startup manually and use the hotkey or voice button.

## First Launch Manual Script

Use this exact script for a clean first-user pass:

1. Reset local app data if needed: `scripts/reset-aura-local.sh`
2. Launch AURA.
3. Confirm you meet AURA on a cinematic first-launch screen with animated avatar and captions.
4. Turn on spoken guidance if desired and press Speak this step.
5. Rename AURA to Alice, then verify the interface changes name and saves it after restart.
6. Step through Privacy + Guardian, workspace, local model, and Start Using AURA.
7. Press Enter command layer.
8. Open a GitHub repo in your browser.
9. Press `Command/Control+Shift+Space` or Refresh context.
10. Confirm "What I can do right now" shows Clone this repo, Summarize README, and Open in local workspace.
11. Press Mic and say `Hey AURA clone this repo`. If speech recognition is available, verify the transcript appears and AURA starts the clone flow. If not, type `Clone this repo locally`.
12. Verify approval is required before shell/file execution.
13. Open Gmail or email, refresh context, and verify Draft reply appears.
14. Try the blocked shell command and verify Guardian blocks it.
15. Try memory rejection with `password=supersecret12345`.
16. Start a build-app prompt and verify it routes toward coding worker/Codex setup instead of pretending local model can do everything.

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
scripts/reset-aura-local.sh
```

The reset script prints these targets and asks for confirmation before archiving:

- `/Applications/AURA.app`
- `~/Library/Application Support/aura-desktop`
- `~/Library/Logs/aura-desktop`
- `~/.aura`

For non-interactive local test cleanup that still archives first:

```bash
scripts/reset-aura-local.sh --yes
```

Permanent deletion is available only when you intentionally ask for it:

```bash
scripts/reset-aura-local.sh --yes --delete
```

## Known Limitations

- The private-alpha macOS app is unsigned and not notarized.
- First launch may require right-click Open or quarantine removal.
- Packaged AURA still depends on local Python 3.10+ and backend Python dependencies; the backend source is bundled in app resources, but Python itself is not embedded yet.
- Ollama model pull progress is shown as an in-app pulling state plus final command output; detailed streaming progress is not yet polished.
- Web Speech API support depends on the Electron/Chromium runtime and microphone permission. Typed command input is the supported fallback.
- Browser/live-site automation is experimental and approval-gated.
- Local models are for private/simple tasks; heavy coding still belongs to Codex or another explicit worker.
- Cloud account, payment, and sync are not required for first-user testing.
