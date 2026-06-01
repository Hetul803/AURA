from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .diff_risk import RiskFinding


def finding_fingerprint(finding: RiskFinding) -> str:
    raw = "|".join([finding.category, finding.path, finding.evidence or finding.explanation])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _path(repo_path: str | Path) -> Path:
    target = Path(repo_path).resolve() / ".aegisure" / "dismissed-findings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def list_dismissed_findings(repo_path: str | Path) -> set[str]:
    target = _path(repo_path)
    if not target.exists():
        return set()
    try:
        return set(json.loads(target.read_text(encoding="utf-8")))
    except Exception:
        return set()


def dismiss_finding(repo_path: str | Path, finding: RiskFinding) -> str:
    dismissed = list_dismissed_findings(repo_path)
    fp = finding_fingerprint(finding)
    dismissed.add(fp)
    _path(repo_path).write_text(json.dumps(sorted(dismissed), indent=2), encoding="utf-8")
    return fp
