from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from aegisure.attribution import attribution_records
from aegisure.constitution import load_constitution, scan_repository
from aegisure.diff_parser import parse_unified_diff
from aegisure.diff_risk import DiffRiskReport, analyze_diff
from aegisure.policy_engine import default_policy_yaml, evaluate_policy
from aegisure.repair_prompt import generate_repair_prompt
from aegisure.second_opinion import heuristic_second_opinion

from .client import GitHubAppClient
from .models import GitHubCheckRun, GitHubWebhookEvent


COMMENT_MARKER = "<!-- aegisure-risk-report -->"


@dataclass(frozen=True)
class PRFlowResult:
    processed: bool
    duplicate: bool = False
    reason: str = ""
    risk_report: dict | None = None
    check_run: dict | None = None
    comment: dict | None = None


def conclusion_for_report(report: DiffRiskReport) -> str:
    if report.verdict == "block":
        return "failure"
    if report.verdict in {"require_review", "caution"}:
        return "neutral"
    return "success"


def render_pr_comment(*, report: DiffRiskReport, repair_prompt: str, second_opinion: dict | None = None) -> str:
    by_severity: dict[str, list[str]] = {}
    for finding in report.findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        by_severity.setdefault(finding.severity, []).append(f"- `{finding.category}` at `{location}` — {finding.explanation}")
    sections = []
    for severity in ["critical", "high", "warning", "info"]:
        items = by_severity.get(severity)
        if items:
            sections.append(f"### {severity.title()} findings\n" + "\n".join(items))
    second = ""
    if second_opinion:
        second = f"\n\n## Cross-model second opinion\n{second_opinion.get('summary') or second_opinion.get('text') or 'No second opinion text.'}"
    return "\n\n".join([
        COMMENT_MARKER,
        "# Aegisure PR Risk Report",
        f"**Verdict:** `{report.verdict}`  \n**Risk score:** `{report.score}/100`",
        report.summary,
        *(sections or ["No risk findings."]),
        "## Request fix prompt",
        "```text\n" + repair_prompt.strip()[:6000] + "\n```",
        "## False positive controls",
        "If a finding is expected, dismiss it in the Aegisure dashboard. The identical pattern will not be re-flagged for this repository.",
        second,
    ])


async def post_or_update_comment(client: GitHubAppClient, *, owner: str, repo: str, number: int, body: str, installation_token: str) -> dict[str, Any]:
    comments = await client.list_pr_comments(owner=owner, repo=repo, number=number, installation_token=installation_token)
    existing = next((comment for comment in comments if COMMENT_MARKER in str(comment.get("body") or "")), None)
    if existing:
        return await client.update_pr_comment(owner=owner, repo=repo, comment_id=int(existing["id"]), body=body, installation_token=installation_token)
    return await client.post_pr_comment(owner=owner, repo=repo, number=number, body=body, installation_token=installation_token)


async def process_pull_request_webhook(
    event: GitHubWebhookEvent,
    *,
    client: GitHubAppClient | None = None,
    policy_yaml: str | None = None,
    enable_second_opinion: bool = False,
) -> PRFlowResult:
    if event.event != "pull_request" or event.action not in {"opened", "synchronize", "reopened", "ready_for_review"}:
        return PRFlowResult(processed=False, reason="ignored_event")
    if not event.installation_id or not event.repository or not event.pull_request:
        return PRFlowResult(processed=False, reason="missing_pr_context")
    client = client or GitHubAppClient()
    token = await client.create_installation_token(event.installation_id)
    repo = event.repository
    pr = event.pull_request
    diff_text = await client.fetch_pull_request_diff(owner=repo.owner, repo=repo.name, number=pr.number, installation_token=token)
    parsed = parse_unified_diff(diff_text)
    # GitHub flow can run without a local checkout; repo-local AEGIS.md is loaded later when fetched/cached.
    report = analyze_diff(parsed)
    policy_eval = evaluate_policy(parsed, policy_text=policy_yaml or default_policy_yaml(), risk_report=report)
    if not policy_eval.passed and report.verdict == "pass":
        report = analyze_diff(parsed)
    repair = generate_repair_prompt(risk_report=report, failed_tests=[], agent="codex")
    second = heuristic_second_opinion(diff_text, author_agent="unknown").to_dict() if enable_second_opinion else None
    body = render_pr_comment(report=report, repair_prompt=repair.prompt, second_opinion=second)
    conclusion = conclusion_for_report(report)
    check = GitHubCheckRun(
        head_sha=pr.head_sha,
        conclusion=conclusion,  # type: ignore[arg-type]
        title=f"Aegisure: {report.verdict}",
        summary=report.summary,
        text=body,
    )
    check_run = await client.create_check_run(owner=repo.owner, repo=repo.name, check_run=check, installation_token=token)
    comment = await post_or_update_comment(client, owner=repo.owner, repo=repo.name, number=pr.number, body=body, installation_token=token)
    change_id = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
    ledger = [record.to_dict() for record in attribution_records(parsed, repo=repo.full_name, change_id=change_id, agent="unknown", source="github_webhook")]
    return PRFlowResult(processed=True, risk_report={**report.to_dict(), "policy_evaluation": policy_eval.to_dict(), "attribution": ledger}, check_run=check_run, comment=comment)
