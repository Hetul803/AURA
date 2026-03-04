from __future__ import annotations
import json
from pathlib import Path
from .db import get_conn

def export_profile(path: str) -> str:
    conn = get_conn()
    data = {}
    for table in ["memories", "preferences", "macros", "actions_log", "events", "profile_meta"]:
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
        data[table] = rows
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path

def import_profile(path: str) -> None:
    conn = get_conn()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    with conn:
        for table, rows in data.items():
            conn.execute(f"DELETE FROM {table}")
            for row in rows:
                keys = list(row.keys())
                vals = [row[k] for k in keys]
                q = ",".join("?" for _ in keys)
                conn.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({q})", vals)
