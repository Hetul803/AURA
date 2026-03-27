from __future__ import annotations
from datetime import datetime, timedelta
from .profile_paths import profile_dir


def enforce_retention(now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    artifacts = profile_dir() / "artifacts"
    stats = {"deleted_raw": 0, "kept_summary": 0}
    for p in artifacts.glob("*"):
        if not p.is_file():
            continue
        age = now - datetime.utcfromtimestamp(p.stat().st_mtime)
        if age > timedelta(days=30) and not p.name.endswith('.summary.json'):
            summary = p.with_suffix(p.suffix + '.summary.json')
            summary.write_text('{"distilled": true}', encoding='utf-8')
            p.unlink()
            stats['deleted_raw'] += 1
            stats['kept_summary'] += 1
    return stats
