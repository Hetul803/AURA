from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .constitution import Constitution
from .diff_risk import DiffRiskReport, RiskFinding


@dataclass(frozen=True)
class RepairPrompt:
    agent: str
    prompt: str
    blocked_paths: tuple[str, ...]
    required_tests: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "prompt": self.prompt,
            "blocked_paths": list(self.blocked_paths),
            "required_tests": list(self.required_tests),
        }


def _finding_lines(findings: Iterable[RiskFinding]) -> list[str]:
    lines = []
    for finding in findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        lines.append(f"- {finding.category} [{finding.severity}] at {location}: {finding.explanation}")
    return lines or ["- No specific findings were recorded; inspect the diff and keep the change scoped."]


def generate_repair_prompt(
    *,
    risk_report: DiffRiskReport,
    constitution: Constitution | None = None,
    failed_tests: list[str] | None = None,
    repo_memory: list[str] | None = None,
    agent: str = "codex",
) -> RepairPrompt:
    protected_paths = tuple(constitution.protected_paths if constitution else [])
    test_commands = tuple((failed_tests or []) or (constitution.test_commands if constitution else []) or ["Run the smallest relevant regression test."])
    memory = repo_memory or []
    prompt = "\n".join([
        f"You are {agent}, repairing an Aegisure-reviewed change.",
        "",
        "Fix only the risks listed below. Do not broaden scope, do not rewrite unrelated code, and do not touch protected paths unless the fix is directly required.",
        "",
        "Risk findings:",
        *_finding_lines(risk_report.findings),
        "",
        "Repo rules to preserve:",
        *(f"- {rule}" for rule in (constitution.agent_rules if constitution else ["Keep the change minimal and safe."])),
        "",
        "Protected paths:",
        *(f"- `{path}`" for path in protected_paths or ("None detected.",)),
        "",
        "Relevant repo memory:",
        *(f"- {item}" for item in memory or ["None supplied."]),
        "",
        "Required repair loop:",
        "- inspect the exact risky lines",
        "- remove secrets or unsafe commands instead of masking symptoms",
        "- preserve public behavior unless explicitly asked to change it",
        "- add or update a regression test when behavior changes",
        "- run the checks below or explain why they cannot run",
        "",
        "Checks:",
        *(f"- `{command}`" for command in test_commands),
        "",
        "Final response must include changed files, tests run, residual risk, and whether human approval is still required.",
    ])
    return RepairPrompt(agent=agent, prompt=prompt, blocked_paths=protected_paths, required_tests=test_commands)
