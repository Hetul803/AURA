from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .diff_risk import DiffRiskReport, analyze_diff
from .llm_provider import LLMProvider


@dataclass(frozen=True)
class SecondOpinion:
    reviewer: str
    status: str
    agreement: str
    concerns: list[str]
    summary: str
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "status": self.status,
            "agreement": self.agreement,
            "concerns": self.concerns,
            "summary": self.summary,
            "raw": self.raw,
        }


def heuristic_second_opinion(diff_text: str, *, author_agent: str = "unknown", risk_report: DiffRiskReport | None = None) -> SecondOpinion:
    report = risk_report or analyze_diff(diff_text)
    concerns = [f"{finding.category}: {finding.explanation}" for finding in report.findings[:8]]
    agreement = "disagree" if report.verdict in {"block", "require_review"} else "agree"
    summary = f"Static reviewer {'does not accept' if agreement == 'disagree' else 'accepts'} the {author_agent} change as-is. {report.summary}"
    return SecondOpinion(reviewer="aura-static-reviewer", status="completed", agreement=agreement, concerns=concerns, summary=summary)


async def cross_model_second_opinion(
    diff_text: str,
    *,
    author_agent: str,
    reviewer: str = "anthropic",
    model: str | None = None,
    risk_report: DiffRiskReport | None = None,
) -> SecondOpinion:
    report = risk_report or analyze_diff(diff_text)
    prompt = (
        "Review this AI-generated code diff as a second-opinion safety reviewer. "
        "Return concise concerns, agreement/disagreement, and whether human review is required.\n\n"
        f"Author agent: {author_agent}\nRisk report: {report.to_dict()}\n\nDiff:\n{diff_text[:12000]}"
    )
    provider = LLMProvider(reviewer if reviewer in {"anthropic", "openai", "ollama"} else "anthropic", model=model)
    response = await provider.complete(prompt)
    if response.status == "completed":
        return SecondOpinion(response.provider, "completed", "reviewed", [], response.text, raw=response.text)
    return SecondOpinion(reviewer, "unavailable", "unknown", [response.reason] if response.reason else [], f"{reviewer} second opinion is not configured or the daily cap was reached; static review remains available.")
