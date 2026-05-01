# AURA Private Alpha Runbook

This runbook is for private alpha builds only. AURA is still a local-first desktop product with experimental orchestration features.

## Private Alpha Standard

- The constitution must remain the source of truth.
- Profile data stays local by default.
- Risky actions require approval.
- Email send, code push, file delete, spending, uploads, and destructive shell actions must not happen silently.
- User-owned web AI tools such as ChatGPT or Claude are treated as browser sessions owned by the user, not AURA-owned cloud credentials.
- AURA's own planning model route is separate from user-task delegation through the user's subscriptions.

## Readiness Check

Run:

```bash
python infra/scripts/private_alpha_check.py
```

The check verifies required docs, packaging metadata, release targets, and constitution primitives.

## Manual Smoke Test

1. Start the backend.
2. Start the desktop app.
3. Confirm the overlay opens.
4. Run `Summarize this` with selected text or clipboard text.
5. Confirm the draft pauses for approval.
6. Reject once and verify nothing is pasted.
7. Approve once and verify paste-back uses target validation.
8. Run `Use ChatGPT to draft a reply to this email` and verify AURA prepares a prompt and asks before paste.
9. Run `Create a full app for this idea` and verify AURA routes to the coding agent abstraction.
10. Check the memory panel and workflow suggestions.

## Release Notes Checklist

- Include commit SHA.
- Include backend test result.
- Include desktop test/build result or the reason it could not run.
- Include known limitations.
- Include profile storage path.
- Include rollback instructions.

## Known Alpha Limitations

- Desktop packaging depends on Node and pnpm being available.
- Codex, ChatGPT, Claude, and local models require user configuration or browser sessions.
- Phone, home, car, and enterprise surfaces are adapter contracts and specs at this stage.
- Browser automation is safety-gated but still needs more live-site hardening.
