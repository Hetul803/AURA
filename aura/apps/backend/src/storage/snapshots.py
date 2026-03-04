from __future__ import annotations
from datetime import datetime
import shutil
from .profile_paths import profile_dir

def create_snapshot() -> str:
    base = profile_dir()
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    dest = base / "snapshots" / ts
    dest.mkdir(parents=True, exist_ok=True)
    db = base / "aura.sqlite3"
    if db.exists():
        shutil.copy2(db, dest / "aura.sqlite3")
    return ts
