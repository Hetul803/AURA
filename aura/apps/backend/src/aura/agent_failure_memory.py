from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class AgentFailureRecord:
    repo: str
    agent: str
    failure_class: str
    summary: str
    repair_worked: bool | None = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "agent": self.agent,
            "failure_class": self.failure_class,
            "summary": self.summary,
            "repair_worked": self.repair_worked,
            "created_at": self.created_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }


def record_agent_failure(repo_path: str | Path, record: AgentFailureRecord) -> Path:
    target_dir = Path(repo_path).resolve() / ".aura"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "agent-failure-memory.jsonl"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
    return target


def list_agent_failures(repo_path: str | Path, *, agent: str | None = None) -> list[dict]:
    target = Path(repo_path).resolve() / ".aura" / "agent-failure-memory.jsonl"
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if agent and row.get("agent") != agent:
            continue
        rows.append(row)
    return rows
