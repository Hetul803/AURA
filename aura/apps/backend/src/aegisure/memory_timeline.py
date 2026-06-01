from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class MemoryTimelineEvent:
    workspace_id: str
    repo_id: str
    agent: str
    event_type: str
    summary: str
    payload: dict
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": f"memevt_{uuid4().hex}",
            "workspace_id": self.workspace_id,
            "repo_id": self.repo_id,
            "agent": self.agent,
            "event_type": self.event_type,
            "summary": self.summary,
            "payload": self.payload,
            "created_at": self.created_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }


def append_local_memory_event(repo_path: str | Path, event: MemoryTimelineEvent) -> Path:
    target_dir = Path(repo_path).resolve() / ".aegisure"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "memory-timeline.jsonl"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
    return target


def list_local_memory_timeline(repo_path: str | Path, *, workspace_id: str | None = None, agent: str | None = None) -> list[dict]:
    target = Path(repo_path).resolve() / ".aegisure" / "memory-timeline.jsonl"
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if workspace_id and row.get("workspace_id") != workspace_id:
            continue
        if agent and row.get("agent") != agent:
            continue
        rows.append(row)
    return sorted(rows, key=lambda item: item.get("created_at", ""))
