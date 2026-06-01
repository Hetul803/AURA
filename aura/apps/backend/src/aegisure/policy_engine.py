from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

import yaml

from .diff_parser import ParsedDiff, parse_unified_diff
from .diff_risk import DiffRiskReport, analyze_diff


@dataclass(frozen=True)
class PolicyViolation:
    rule_id: str
    severity: str
    decision: str
    explanation: str
    matched_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "decision": self.decision,
            "explanation": self.explanation,
            "matched_paths": list(self.matched_paths),
        }


@dataclass(frozen=True)
class PolicyEvaluation:
    passed: bool
    violations: tuple[PolicyViolation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": [violation.to_dict() for violation in self.violations]}


def load_policy_rules(policy_text: str | None) -> list[dict[str, Any]]:
    if not policy_text:
        return []
    data = yaml.safe_load(policy_text) if policy_text.strip() else {}
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        rules = data.get("rules", [])
        return [item for item in rules if isinstance(item, dict)]
    raise ValueError("Policy YAML must contain a list or a top-level rules list")


def _path_matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) or path.startswith(pattern.rstrip("/") + "/") for pattern in patterns)


def evaluate_policy(
    diff: str | ParsedDiff,
    *,
    policy_text: str,
    risk_report: DiffRiskReport | None = None,
) -> PolicyEvaluation:
    parsed = parse_unified_diff(diff) if isinstance(diff, str) else diff
    report = risk_report or analyze_diff(parsed)
    rules = load_policy_rules(policy_text)
    violations: list[PolicyViolation] = []
    changed_paths = [file.path for file in parsed.files]
    finding_categories = {finding.category for finding in report.findings}
    for rule in rules:
        rule_id = str(rule.get("id") or rule.get("name") or "unnamed_rule")
        paths = [str(item) for item in (rule.get("paths") or rule.get("path_patterns") or [])]
        categories = {str(item) for item in (rule.get("categories") or rule.get("risk_categories") or [])}
        min_score = int(rule.get("min_score") or 0)
        matched_paths = tuple(path for path in changed_paths if _path_matches(path, paths)) if paths else tuple(changed_paths)
        category_hit = bool(categories & finding_categories) if categories else True
        score_hit = report.score >= min_score if min_score else True
        if matched_paths and category_hit and score_hit:
            decision = str(rule.get("decision") or ("block" if rule.get("block") else "require_review"))
            violations.append(
                PolicyViolation(
                    rule_id=rule_id,
                    severity=str(rule.get("severity") or ("blocked" if decision == "block" else "high")),
                    decision=decision,
                    explanation=str(rule.get("description") or rule.get("explanation") or f"Policy `{rule_id}` matched this diff."),
                    matched_paths=matched_paths,
                )
            )
    return PolicyEvaluation(passed=not violations, violations=tuple(violations))


def default_policy_yaml() -> str:
    return """rules:
  - id: protected_payments
    description: Payment and billing files require human review.
    paths: ["*payment*", "*billing*", "*stripe*", "*checkout*"]
    decision: require_review
    severity: high
  - id: auth_boundary
    description: Auth, session, role, permission, and OAuth changes require human review.
    paths: ["*auth*", "*session*", "*oauth*", "*permission*", "*role*"]
    decision: require_review
    severity: high
  - id: secret_or_destructive_change
    description: Secrets or destructive shell commands are blocked.
    categories: ["secret_in_diff", "destructive_shell_command"]
    decision: block
    severity: critical
"""


def policy_json(evaluation: PolicyEvaluation) -> str:
    return json.dumps(evaluation.to_dict(), indent=2, sort_keys=True)
