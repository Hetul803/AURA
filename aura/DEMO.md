# AURA Developer Pivot Demo

## Goal

Show AURA as the trust, memory, and control layer for AI coding agents.

## Local CLI demo

```bash
cd apps/backend
PYTHONPATH=src python -m aura.cli init --path /path/to/demo-repo
PYTHONPATH=src python -m aura.cli export --path /path/to/demo-repo
```

Open the generated files:

- `AURA.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.cursorrules`
- `.clinerules`
- `.github/copilot-instructions.md`

Explain: one project Constitution becomes memory for every coding agent.

## Risk scan demo

Create or stage a risky diff:

```bash
echo 'password = "hunter22222"' >> app.py
git add app.py
PYTHONPATH=src python -m aura.cli scan --path . --staged
```

Expected result: AURA blocks the change because the diff contains a secret-like value.

## Repair prompt demo

```bash
PYTHONPATH=src python -m aura.cli repair --path . --staged --agent codex
```

Expected result: A constrained repair prompt that tells the agent exactly what to fix, what not to touch, and which tests to run.

## Provenance demo

```bash
PYTHONPATH=src python -m aura.cli commit -m "fix auth guard" --agent codex --prompt "Remove the leaked token and add a regression test"
```

Expected result: the commit message includes AURA trailers and `.aura/attribution-ledger.jsonl` records which files Codex touched.

## Dashboard demo

```bash
pnpm --filter aura-web dev
```

Open the dashboard and show:

1. Landing page positioning.
2. Risk Report hero screen.
3. Constitution editor.
4. Cross-agent memory export.
5. Attribution and provenance pages.
6. Policy editor.

## GitHub App demo shape

For the first live GitHub App test, configure:

- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY_PATH`
- `GITHUB_WEBHOOK_SECRET`
- `AURA_API_TOKEN`

Then send a signed pull request webhook to `/github/webhook`. AURA verifies the HMAC signature and rejects duplicates by delivery id.
