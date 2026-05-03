# AURA v1 Spec

AURA v1 is a desktop-first, local-first AI operating layer. It is not a chatbot. The app should feel like a command center for the user's computer.

## Core Loop

1. Capture current desktop/browser/workspace context.
2. Interpret the user command.
3. Plan typed steps using registered tools.
4. Run low-risk steps automatically.
5. Pause risky steps for approval.
6. Block dangerous steps.
7. Show the run timeline, approval cards, Guardian events, and final result.
8. Learn useful preferences/workflows without storing secrets.

## Required Product Surfaces

- Current context card: what AURA can see.
- Command center: launch flows and typed command input.
- Run timeline: active steps, errors, retries, and status.
- Approval cards: approve, reject, retry, edit, or resume.
- AURA Guardian panel: protection status, risk explanations, redacted audit events.
- Memory panel: editable scoped memory, quality, compaction, storage stats.
- Workflow panel: saved workflows, suggestions, replay, repair/failure history.
- Cost/model/profile panel: local profile, model/cost metadata, tool registry.
- Onboarding: privacy, Guardian, permissions, memory, model/cost, workspace, optional bridges.

## Launch Flows For Private Alpha

- Clone current GitHub repository.
- Draft reply.
- Summarize selected text.
- Build/create app through coding agent routing.
- Use ChatGPT/Claude browser handoff.
- Run or save a reusable workflow.

## Safety Rules

- Never send email without explicit approval.
- Never paste into an external app without explicit approval.
- Never run risky shell commands without explicit approval.
- Never run blocked destructive shell commands.
- Never store secrets in memory.
- Never replay risky workflows silently.
- Never export/import memory without path validation and redaction.
- Panic stop must cancel active runs.

## Current Known Limits

- Voice transcription is still a stub.
- Real drafting depends on local Ollama/model readiness unless using deterministic fallback paths.
- Packaging is private-alpha and unsigned by default.
- Browser/live-site automation is still experimental and should stay approval-gated.
- Phone/home/car/enterprise surfaces are contracts, not full products.
