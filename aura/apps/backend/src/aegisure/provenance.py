from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


# Keep the original trailer protocol stable so pre-rebrand provenance remains readable.
TRAILER_AGENT = "AURA-Agent"
TRAILER_PROMPT_HASH = "AURA-Prompt-SHA256"
TRAILER_PROMPT = "AURA-Prompt"


@dataclass(frozen=True)
class ProvenanceRecord:
    change_id: str
    agent: str
    prompt_hash: str
    prompt_excerpt: str
    commit_sha: str | None = None
    source: str = "cli"
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "agent": self.agent,
            "prompt_hash": self.prompt_hash,
            "prompt_excerpt": self.prompt_excerpt,
            "commit_sha": self.commit_sha,
            "source": self.source,
            "created_at": self.created_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()


def build_commit_message(message: str, *, agent: str, prompt: str) -> str:
    excerpt = " ".join((prompt or "").split())[:180]
    return "\n\n".join([
        message.strip(),
        f"{TRAILER_AGENT}: {agent}",
        f"{TRAILER_PROMPT_HASH}: {prompt_hash(prompt)}",
        f"{TRAILER_PROMPT}: {excerpt}",
    ])


def parse_provenance_text(text: str) -> ProvenanceRecord | None:
    trailers: dict[str, str] = {}
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {TRAILER_AGENT, TRAILER_PROMPT_HASH, TRAILER_PROMPT}:
            trailers[key] = value.strip()
    if not trailers.get(TRAILER_AGENT):
        return None
    change_id = trailers.get(TRAILER_PROMPT_HASH) or prompt_hash(trailers.get(TRAILER_PROMPT, ""))
    return ProvenanceRecord(
        change_id=change_id,
        agent=trailers[TRAILER_AGENT],
        prompt_hash=trailers.get(TRAILER_PROMPT_HASH, change_id),
        prompt_excerpt=trailers.get(TRAILER_PROMPT, ""),
        source="trailer",
    )


def record_git_note(repo_path: str | Path, commit_sha: str, record: ProvenanceRecord) -> bool:
    proc = subprocess.run(
        ["git", "notes", "--ref", "aura/provenance", "add", "-f", "-m", json.dumps(record.to_dict(), sort_keys=True), commit_sha],
        cwd=Path(repo_path).resolve(),
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def read_commit_provenance(repo_path: str | Path, commit_sha: str = "HEAD") -> ProvenanceRecord | None:
    proc = subprocess.run(["git", "show", "-s", "--format=%B", commit_sha], cwd=Path(repo_path).resolve(), capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    record = parse_provenance_text(proc.stdout)
    if not record:
        return None
    sha_proc = subprocess.run(["git", "rev-parse", commit_sha], cwd=Path(repo_path).resolve(), capture_output=True, text=True)
    sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else commit_sha
    return ProvenanceRecord(**{**record.to_dict(), "commit_sha": sha})
