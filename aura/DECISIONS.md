# Aegisure Pivot Decisions

## 2026-05-31: Phase 1 starts with the local core

- Decision: keep the existing FastAPI/Python core and add repo-analysis modules under `apps/backend/src/aura`.
- Why: the reusable moat is in privacy, safety, approval, audit, memory, and identity logic; the consumer desktop shell is not needed for the GitHub-first developer pivot.
- Tradeoff: M1 ships as a local CLI plus importable core before the GitHub App/dashboard are built.

## 2026-05-31: AEGIS.md is the canonical Constitution

- Decision: generate `AEGIS.md` as the first canonical cross-agent memory file.
- Why: it is human-readable, repo-local, easy to review in PRs, and can later export into `AGENTS.md`, `CLAUDE.md`, Cursor, Cline/Roo, and Copilot formats.
- Tradeoff: early Constitution generation is heuristic until GitHub history and team policy data are available.

## 2026-05-31: Diff analysis is static and constrained

- Decision: M1 risk analysis parses unified diffs and never executes changed code.
- Why: Aegisure's trust layer must be safe by construction.
- Tradeoff: some findings are conservative and may require human tuning through policy rules later.

## 2026-05-31: Rebrand keeps provenance protocol stable

- Decision: user-facing product and package names move to Aegisure, but the existing `AURA-Agent` commit trailers and `aura/provenance` git-note namespace stay readable for compatibility.
- Why: provenance and attribution are the data moat; renaming the wire format would split pre- and post-rebrand history.
- Migration note: new environment variables use `AEGISURE_` prefixes. During migration, set both old and new prefixes only if a legacy desktop process still depends on the old names.

## 2026-05-31: Free static core is LLM-free

- Decision: diff parsing, secret detection, auth/CORS/dependency/test-removal/destructive-command detection, policy evaluation, provenance, attribution, and basic summaries do not call an LLM.
- Why: the core PR check must run on every scan/commit/PR at zero marginal cost and with no API key.
- Tradeoff: LLM reasoning is opt-in and metered through `LLMProvider`.
