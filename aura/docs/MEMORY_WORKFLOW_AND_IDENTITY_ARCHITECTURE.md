# AURA Memory, Workflow, and Identity Architecture

This document defines the local-first brain layer for AURA. It extends the product constitution with implementation rules for durable memory, reusable workflows, workflow repair, and subscription-ready profile identity.

## Principles

- Memory is local-first, private by default, editable, exportable, and recoverable.
- AURA should remember useful patterns, not junk logs.
- Memory should improve behavior through retrieval, reinforcement, compaction, and lifecycle management.
- Workflows should be versioned products, not untracked command snippets.
- Identity and subscription data must not break local-only usage.
- Cloud sync and billing are architecture hooks until explicitly implemented.

## Memory Model

Typed memory records live in `memory_items`.

Core fields:

- `scope`: `personal`, `work`, `company`, `session`, or `device`.
- `kind`: `preference`, `workflow`, `fact`, `person`, `project`, `failure`, `fix`, `safety`, `context`, `summary`, `note`, or `execution`.
- `memory_key`: stable key such as `writing.tone`, `github.clone.folder`, or `paste.failure.gmail`.
- `value`: human-readable memory value.
- `confidence`: model/user confidence from `0.0` to `1.0`.
- `source`: `manual`, `user`, `legacy_memory`, `learning`, `compaction`, or integration-specific source.
- `permission`: usually `private`; sensitive data must never be shared.
- `tags`: retrieval hints and task labels.
- `provenance`: origin, source run, raw memory IDs, or compaction evidence.
- `user_notes`: user-editable notes.
- `usage_count` and `last_used_at`: retrieval/reinforcement signals.
- `archived`: soft-delete/lifecycle state.

## Memory Quality

AURA rejects low-value memories before storage:

- empty or trivial values like `ok`, `done`, or `n/a`;
- unknown memory kinds;
- missing keys;
- sensitive-looking content unless permission is private/sensitive;
- low-confidence auto memories.

Duplicate memories are reinforced instead of stored again. Reinforcement increases usage count, updates last-used time, records evidence, and gently raises confidence.

## Memory Lifecycle

AURA memory follows this lifecycle:

1. New memory: passes quality gate, stores provenance.
2. Reinforcement: duplicate or successful reuse increases confidence/usage.
3. Update: user or system can edit value, scope, tags, permission, notes, and metadata.
4. Decay: stale non-pinned memories lose confidence over time.
5. Archive: stale low-confidence memories are hidden but recoverable.
6. Delete: explicit user delete removes the row.
7. Merge: exact duplicates archive into a keeper record.
8. Compact: old related memories become summary memories with raw IDs preserved.

Safety memories and pinned memories are protected from automatic archive.

## Memory Retrieval

Retrieval ranking combines:

- text relevance;
- lightweight semantic distance;
- recency;
- confidence;
- usage count;
- pinned status;
- scope match;
- task match;
- permission match.

Retrieval updates `usage_count` and `last_used_at`, so useful memories become easier to find later.

## Memory Compaction

Compaction groups old related memories by scope and kind, creates a `summary` memory, and archives the raw records. The summary preserves provenance:

- raw memory IDs;
- compacted kind;
- raw count;
- compaction timestamp.

Important user preferences, safety rules, and pinned memories should be preserved as standalone records unless the user explicitly edits them.

## Workflow Model

Reusable workflows live in `workflow_templates`.

Workflow fields include:

- name and description;
- trigger type/value or phrase;
- command template;
- required context;
- approval policy;
- safety class;
- repair strategy;
- linked memories;
- active version;
- success/failure counts;
- last failure reason.

## Workflow Versioning

Every workflow starts with version `1` in `workflow_versions`. Meaningful template changes create a new version and archive the previous active version.

Versions track:

- command template;
- steps;
- required context;
- approval requirements;
- safety class;
- repair strategy;
- linked memories;
- changelog;
- success/failure counts;
- last failure reason.

## Workflow Repair

Workflow repair records live in `workflow_repair_records`.

Each record captures:

- failed workflow/version/run;
- failed step;
- failure reason;
- repair summary;
- whether repair succeeded;
- whether the workflow template should be updated.

Repeated failures create update suggestions. AURA should propose a revised version while preserving older versions for audit and rollback.

## Identity and Subscription Readiness

Local profile/subscription hooks live in `local_profile_account`.

Fields include:

- local profile ID and local user ID;
- future cloud account ID;
- subscription tier;
- free trial state;
- billing status;
- usage limits;
- model cost limits;
- device limit;
- cloud sync enabled flag;
- memory sync identity;
- user-owned cloud storage target;
- metadata.

Default state is local-only:

- `subscription_tier = local_free`;
- `billing_status = local_only`;
- `cloud_sync_enabled = false`;
- no cloud provider selected.

## User-Owned Cloud Future

AURA must remain portable:

- memory export bundle includes memories, workflows, versions, repairs, identity hooks, learning records, approvals, and audit logs;
- encrypted backup bundle should be added before any cloud sync;
- possible user-owned targets: Google Drive, iCloud, Dropbox, S3/R2, Supabase;
- restore must rebuild memory and workflow state from the bundle.

No memory uploads happen until the user explicitly enables sync and chooses a provider.

## APIs

Current backend hooks:

- `POST /memory/search`
- `PATCH /memory/items/{memory_id}`
- `DELETE /memory/items/{memory_id}`
- `POST /memory/items/{memory_id}/reinforce`
- `POST /memory/compact`
- `POST /memory/lifecycle-sweep`
- `POST /profile/export`
- `POST /workflows`
- `POST /workflows/{workflow_id}/run`
- `GET /workflows/{workflow_id}/versions`
- `POST /workflows/{workflow_id}/versions`
- `GET /workflows/{workflow_id}/repairs`
- `POST /workflows/{workflow_id}/repairs`
- `GET /workflows/{workflow_id}/update-suggestions`
- `GET /profile/status`
- `PATCH /profile/status`

## Non-Goals For Now

- No payment processor.
- No real cloud sync.
- No automatic upload of memory.
- No enterprise policy server.
- No background memory deletion without a recoverable archive phase.
