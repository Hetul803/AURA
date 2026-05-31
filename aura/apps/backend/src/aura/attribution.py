from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .diff_parser import ParsedDiff


KNOWN_AGENTS = {
    "codex": ("codex", "openai codex"),
    "claude-code": ("claude", "claude code"),
    "cursor": ("cursor",),
    "copilot": ("copilot", "github copilot"),
    "cline": ("cline",),
    "roo": ("roo", "roo code"),
}


@dataclass(frozen=True)
class AttributionRecord:
    repo: str
    change_id: str
    path: str
    agent: str
    source: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "change_id": self.change_id,
            "path": self.path,
            "agent": self.agent,
            "source": self.source,
            "created_at": self.created_at,
        }


def infer_agent(*, commit_message: str = "", pr_body: str = "", explicit_agent: str | None = None) -> str:
    if explicit_agent:
        return explicit_agent
    text = f"{commit_message}\n{pr_body}".lower()
    trailer = re.search(r"aura-agent:\s*([a-z0-9_.-]+)", text)
    if trailer:
        return trailer.group(1)
    for agent, needles in KNOWN_AGENTS.items():
        if any(needle in text for needle in needles):
            return agent
    return "unknown"


def attribution_records(parsed: ParsedDiff, *, repo: str, change_id: str, agent: str, source: str = "analysis") -> list[AttributionRecord]:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return [AttributionRecord(repo=repo, change_id=change_id, path=file.path, agent=agent, source=source, created_at=now) for file in parsed.files]


def append_attribution_ledger(repo_path: str | Path, records: list[AttributionRecord]) -> Path:
    aura_dir = Path(repo_path).resolve() / ".aura"
    aura_dir.mkdir(parents=True, exist_ok=True)
    target = aura_dir / "attribution-ledger.jsonl"
    with target.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
    return target


def query_attribution_ledger(repo_path: str | Path, *, agent: str | None = None) -> list[dict]:
    target = Path(repo_path).resolve() / ".aura" / "attribution-ledger.jsonl"
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
