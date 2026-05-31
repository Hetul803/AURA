# AURA Pivot Decisions

## 2026-05-31: Phase 1 starts with the local core

- Decision: keep the existing FastAPI/Python core and add repo-analysis modules under `apps/backend/src/aura`.
- Why: the reusable moat is in privacy, safety, approval, audit, memory, and identity logic; the consumer desktop shell is not needed for the GitHub-first developer pivot.
- Tradeoff: M1 ships as a local CLI plus importable core before the GitHub App/dashboard are built.

## 2026-05-31: AURA.md is the canonical Constitution

- Decision: generate `AURA.md` as the first canonical cross-agent memory file.
- Why: it is human-readable, repo-local, easy to review in PRs, and can later export into `AGENTS.md`, `CLAUDE.md`, Cursor, Cline/Roo, and Copilot formats.
- Tradeoff: early Constitution generation is heuristic until GitHub history and team policy data are available.

## 2026-05-31: Diff analysis is static and constrained

- Decision: M1 risk analysis parses unified diffs and never executes changed code.
- Why: AURA's trust layer must be safe by construction.
- Tradeoff: some findings are conservative and may require human tuning through policy rules later.
