# Privacy

AURA is private by default. The current product assumes a local desktop profile, local storage, and explicit user approval before risky actions.

## Local-First Defaults

- Profile data lives in the local AURA profile directory.
- Cloud sync is off.
- Billing/payment is not required.
- User-owned ChatGPT, Claude, or other web AI sessions are treated as browser handoffs, not AURA-owned credentials.
- Local model routing is preferred for private drafting when available.

## Memory Boundaries

Typed memory supports these scopes:

- `personal`
- `work`
- `company`
- `session`
- `device`

Memory records keep provenance, tags, confidence, permission, usage counts, archive state, and compaction metadata. Personal, work, and company memory should not be merged silently. Company-sensitive data must not enter personal memory by default.

## What Memory Should Store

Good memory:

- writing tone preferences;
- repeated workflow preferences;
- safe project/workspace folders;
- prior failures and fixes;
- user-approved safety preferences.

Bad memory:

- passwords;
- API keys;
- private keys;
- raw tokens;
- payment cards;
- SSNs;
- confidential work details without permission.

AURA rejects secret-looking memory writes before storage. Sensitive non-secret memory requires private/sensitive permission.

## Redaction

AURA redacts secrets before persisting:

- run events;
- audit log payloads;
- approval payloads;
- profile export bundles;
- code-run stdout/stderr observations;
- legacy and typed memory values.

## Export and Import

Profile export/import paths are normalized into the local profile export area when relative paths are used. Path traversal is blocked. Profile imports containing detected secrets are rejected.

## Manual Privacy Smoke

1. Open onboarding and select a memory scope.
2. Save local profile settings.
3. Create a normal memory and verify it appears in the Memory panel.
4. Try to create memory containing `password=supersecret12345`; verify it is rejected.
5. Export a profile bundle and verify obvious tokens are redacted.
6. Check Guardian and audit panels after a run; verify secret-looking text is not exposed.
