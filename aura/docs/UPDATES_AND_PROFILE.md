# Updates and Profile

The private alpha profile is local-only by default.

## Local Profile

The backend initializes `local_profile_account` with:

- `subscription_tier = local_free`
- `billing_status = local_only`
- `cloud_sync_enabled = false`
- local-only model and usage limits

Onboarding saves local settings into profile metadata and usage limits. These settings are intentionally subscription-ready but do not require payment or a cloud account.

## Profile Data Included In Export

Exports include:

- legacy memories and typed memory items;
- workflows, workflow versions, and repair records;
- profile identity hooks;
- run records and run events;
- approvals and audit logs;
- learning records;
- context snapshots.

Secrets are redacted before export. Relative export paths are written under the local profile export directory.

## Import Rules

Imports are local file operations only. AURA blocks:

- path traversal;
- unknown tables;
- profile bundles containing detected secrets.

## Updates

Private-alpha updates are manual for now. Release notes should include:

- commit SHA;
- tests run;
- known limitations;
- rollback path;
- profile storage path;
- security/privacy changes.
