from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .diff_risk import DiffRiskReport, analyze_diff


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
    if reviewer == "openai" and os.getenv("OPENAI_API_KEY"):
        try:
            from openai import AsyncOpenAI  # type: ignore

            client = AsyncOpenAI()
            response = await client.responses.create(model=model or os.getenv("AURA_OPENAI_REVIEW_MODEL", "gpt-4.1-mini"), input=prompt)
            text = getattr(response, "output_text", "") or str(response)
            return SecondOpinion("openai", "completed", "reviewed", [], text, raw=text)
        except Exception as exc:
            return SecondOpinion("openai", "unavailable", "unknown", [str(exc)], "OpenAI second opinion could not run.")
    if reviewer == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        try:
            from anthropic import AsyncAnthropic  # type: ignore

            client = AsyncAnthropic()
            response = await client.messages.create(model=model or os.getenv("AURA_ANTHROPIC_REVIEW_MODEL", "claude-3-5-haiku-latest"), max_tokens=800, messages=[{"role": "user", "content": prompt}])
            text = "\n".join(block.text for block in response.content if getattr(block, "type", "") == "text")
            return SecondOpinion("anthropic", "completed", "reviewed", [], text, raw=text)
        except Exception as exc:
            return SecondOpinion("anthropic", "unavailable", "unknown", [str(exc)], "Anthropic second opinion could not run.")
    return SecondOpinion(reviewer, "unavailable", "unknown", [], f"{reviewer} second opinion is not configured; using local static review is available.")
