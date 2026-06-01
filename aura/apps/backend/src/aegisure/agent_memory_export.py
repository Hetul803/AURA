from __future__ import annotations

from pathlib import Path

from .constitution import Constitution, constitution_for_repo, render_constitution


EXPORT_TARGETS = (
    "AEGIS.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".clinerules",
    ".github/copilot-instructions.md",
)


def _rules_block(constitution: Constitution) -> str:
    return "\n".join(f"- {rule}" for rule in constitution.agent_rules)


def _approval_block(constitution: Constitution) -> str:
    return "\n".join(f"- {rule}" for rule in constitution.approval_rules)


def _test_block(constitution: Constitution) -> str:
    return "\n".join(f"- `{command}`" for command in constitution.test_commands) or "- No test command detected yet."


def _protected_block(constitution: Constitution) -> str:
    return "\n".join(f"- `{path}`" for path in constitution.protected_paths) or "- No protected paths detected yet."


def build_memory_exports(constitution: Constitution) -> dict[str, str]:
    shared = {
        "repo": constitution.repo_name,
        "summary": constitution.summary,
        "rules": _rules_block(constitution),
        "approval": _approval_block(constitution),
        "tests": _test_block(constitution),
        "protected": _protected_block(constitution),
    }
    aura_md = render_constitution(constitution)
    agent_md = f"""# Agent Instructions for {shared['repo']}

{shared['summary']}

## Required Behavior
{shared['rules']}

## Human Approval Required
{shared['approval']}

## Protected Paths
{shared['protected']}

## Verification
{shared['tests']}
"""
    claude_md = f"""# Claude Code Memory

You are working in `{shared['repo']}`.

Project summary: {shared['summary']}

Follow these non-negotiable rules:
{shared['rules']}

Before editing protected areas, ask for human review:
{shared['protected']}

Run or recommend these checks:
{shared['tests']}
"""
    cursor_rules = f"""You are an AI coding agent in {shared['repo']}.

{shared['summary']}

Rules:
{shared['rules']}

Protected paths:
{shared['protected']}

Tests:
{shared['tests']}
"""
    cline_rules = f"""# Cline/Roo Rules

Repository: {shared['repo']}

{shared['summary']}

Do:
{shared['rules']}

Require approval:
{shared['approval']}

Verify with:
{shared['tests']}
"""
    copilot = f"""# GitHub Copilot Instructions

This repository uses Aegisure as its project Constitution.

Summary: {shared['summary']}

Coding rules:
{shared['rules']}

Protected paths:
{shared['protected']}

Verification:
{shared['tests']}
"""
    return {
        "AEGIS.md": aura_md,
        "AGENTS.md": agent_md,
        "CLAUDE.md": claude_md,
        ".cursorrules": cursor_rules,
        ".clinerules": cline_rules,
        ".github/copilot-instructions.md": copilot,
    }


def write_memory_exports(repo_path: str | Path, *, overwrite: bool = True) -> list[dict[str, str | bool]]:
    repo = Path(repo_path).resolve()
    exports = build_memory_exports(constitution_for_repo(repo))
    results: list[dict[str, str | bool]] = []
    for target, content in exports.items():
        path = repo / target
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = path.read_text(encoding="utf-8") if path.exists() else None
        changed = previous != content
        if changed and (overwrite or previous is None):
            path.write_text(content, encoding="utf-8")
        results.append({"path": str(path), "target": target, "changed": changed})
    return results
