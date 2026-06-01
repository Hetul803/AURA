from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .constitution import Constitution, check_constitution_violations
from .diff_parser import ChangedFile, ParsedDiff, parse_unified_diff
from .privacy import detect_secret, redact_text
from .safety import classify_shell_command


SEVERITY_SCORE = {"info": 5, "warning": 45, "high": 75, "critical": 100}


@dataclass(frozen=True)
class RiskFinding:
    category: str
    severity: str
    path: str
    explanation: str
    line: int | None = None
    evidence: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "path": self.path,
            "explanation": self.explanation,
            "line": self.line,
            "evidence": redact_text(self.evidence, limit=300),
        }


@dataclass(frozen=True)
class DiffRiskReport:
    score: int
    verdict: str
    findings: tuple[RiskFinding, ...] = ()
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "verdict": self.verdict,
            "summary": self.summary,
            "files_changed": self.files_changed,
            "additions": self.additions,
            "deletions": self.deletions,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _is_path(path: str, *needles: str) -> bool:
    lower = path.lower()
    return any(needle in lower for needle in needles)


def _extension(path: str) -> str:
    return PurePosixPath(path).suffix.lower()


def _line_findings(file: ChangedFile) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    for hunk in file.hunks:
        for line in hunk.lines:
            if line.kind != "add":
                continue
            content = line.content.strip()
            if detect_secret(content):
                findings.append(RiskFinding("secret_in_diff", "critical", file.path, "This added line looks like a secret, token, password, private key, or credential.", line.new_lineno, content))
            if re.search(r"(?i)\b(cors|allow_origins?|access-control-allow-origin)\b", content) and ("*" in content or "true" in content.lower()):
                findings.append(RiskFinding("permissive_cors", "high", file.path, "This change appears to loosen CORS or allow broad origins.", line.new_lineno, content))
            if re.search(r"(?i)\b(stripe|payment|billing|checkout|invoice|subscription)\b", content):
                findings.append(RiskFinding("payment_logic_change", "high", file.path, "Payment or billing logic changed and needs human review.", line.new_lineno, content))
            if re.search(r"(?i)\b(auth|oauth|jwt|session|cookie|permission|role)\b", content):
                findings.append(RiskFinding("auth_change", "high", file.path, "Authentication, authorization, session, or permission logic changed.", line.new_lineno, content))
            if re.search(r"(?i)\b(npm|pnpm|yarn|pip|curl|wget|bash|sh|sudo|rm|dd|mkfs)\b", content):
                shell = classify_shell_command(content)
                if shell.get("blocked") or shell.get("risk") in {"high", "blocked"}:
                    findings.append(RiskFinding("destructive_shell_command", "critical" if shell.get("blocked") else "high", file.path, f"Added shell-like text is risky: {shell.get('reason')}.", line.new_lineno, content))
    return findings


def _file_findings(file: ChangedFile) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    path = file.path
    if file.status == "deleted" and (_is_path(path, "test", "spec") or _extension(path) in {".test.ts", ".spec.ts", ".test.py"}):
        findings.append(RiskFinding("test_removal", "high", path, "A test file was deleted. Agents should add or update tests, not remove coverage."))
    if _is_path(path, ".github/workflows", "dockerfile", "docker-compose", "vercel", "netlify", "fly.toml", "render.yaml"):
        findings.append(RiskFinding("deploy_config_change", "warning", path, "Deployment, CI, or hosting configuration changed."))
    if _is_path(path, "requirements.txt", "package.json", "pnpm-lock.yaml", "package-lock.json", "pyproject.toml"):
        added = file.added_text.lower()
        risky = ["postinstall", "preinstall", "prepare", "curl", "wget", "node-gyp", "eval(", "child_process"]
        if any(token in added for token in risky):
            findings.append(RiskFinding("risky_dependency_added", "high", path, "Dependency or package script change includes a risky install-time pattern.", evidence=file.added_text[:500]))
    if _is_path(path, "migration", "migrations", "alembic") and not re.search(r"(?i)(rollback|downgrade|down)", file.added_text):
        findings.append(RiskFinding("db_migration_without_migration_file", "warning", path, "Database migration changed without an obvious rollback/downgrade path."))
    return findings


def analyze_diff(diff: str | ParsedDiff, *, constitution: Constitution | None = None) -> DiffRiskReport:
    parsed = parse_unified_diff(diff) if isinstance(diff, str) else diff
    findings: list[RiskFinding] = []
    for file in parsed.files:
        findings.extend(_file_findings(file))
        findings.extend(_line_findings(file))

    if len(parsed.files) >= 12 or parsed.additions + parsed.deletions >= 800:
        findings.append(RiskFinding("large_multifile_change", "warning", "*", "This is a large multi-file change; require careful review."))

    if constitution:
        for item in check_constitution_violations([file.path for file in parsed.files], constitution):
            findings.append(RiskFinding(item["category"], item["severity"], item["path"], item["explanation"]))

    score = max([SEVERITY_SCORE.get(finding.severity, 45) for finding in findings] or [0])
    if any(finding.severity == "critical" for finding in findings):
        verdict = "block"
    elif score >= 75:
        verdict = "require_review"
    elif score >= 45:
        verdict = "caution"
    else:
        verdict = "pass"
    summary = f"{len(parsed.files)} files changed, {parsed.additions} additions, {parsed.deletions} deletions, {len(findings)} risk findings."
    return DiffRiskReport(score=score, verdict=verdict, findings=tuple(findings), files_changed=len(parsed.files), additions=parsed.additions, deletions=parsed.deletions, summary=summary)
