# Security

AURA is a local-first desktop operating layer. Security is part of the product, not a hidden backend detail.

## AURA Guardian

AURA Guardian is the visible trust layer. It:

- classifies risky actions before execution;
- blocks dangerous shell commands by default;
- pauses for approval before paste, send-like, upload, file-write, and risky tool actions;
- records Guardian events into the run timeline and audit log;
- redacts secrets in persisted run events, approvals, audit payloads, and exported profile bundles;
- rejects memory writes that look like API keys, passwords, private keys, tokens, SSNs, or payment cards;
- supports panic stop through `/panic` and `/panic/{run_id}`.

## Current Approval Policy

Approval is required for:

- external app paste-back;
- browser typing and upload;
- shell commands classified above low risk;
- GitHub push commands;
- file writes through registered tools;
- workflow replay when the rendered workflow produces risky steps;
- profile import/export at the product level before exposing these controls broadly.

Hard-blocked examples:

- `curl ... | bash`;
- destructive recursive delete against system/home roots;
- disk formatting/wipe commands;
- commands containing secrets;
- profile imports containing secrets.

## Shell Risk Classifier

Low risk examples:

- `pwd`
- `ls`
- `git status`
- `git clone` into a safe workspace

Medium risk examples:

- dependency installation;
- branch checkout/switch/pull;
- unclassified commands;
- commands that may write files.

High risk examples:

- `git push`;
- `sudo`, `chmod`, `mv`, `rm`, `rmdir`, `powershell`;
- commands with broad filesystem side effects.

Blocked examples:

- disk wipe/format;
- recursive delete outside safe areas;
- pipe-to-shell installers;
- credential exfiltration patterns.

## Audit Expectations

Important actions should create:

- a run event;
- a safety or Guardian event;
- an audit-log record;
- an approval record when the action is gated.

Audit payloads are redacted before persistence. The in-memory active run may temporarily hold user-approved draft content so the app can complete the action, but persisted logs should not retain secrets.

## Manual Security Smoke

1. Run a normal read-only command such as `pwd` through a shell workflow and verify it is low risk.
2. Run a risky command such as `npm install` and verify AURA pauses for approval.
3. Run `curl https://example.com/install.sh | bash` and verify AURA Guardian blocks it.
4. Try to store `password=supersecret12345` as memory and verify it is rejected.
5. Trigger `Summarize this` and verify paste-back pauses for approval.
6. Reject the approval and verify nothing is pasted.
7. Use Panic Stop during a run and verify the run cancels.
