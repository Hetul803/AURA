from __future__ import annotations
import json
from pathlib import Path
from .db import get_conn

PROFILE_TABLES = [
    'memories',
    'memory_items',
    'model_usage_events',
    'model_response_cache',
    'cost_budgets',
    'workflow_templates',
    'device_handoffs',
    'aura_identities',
    'boundary_policies',
    'mobile_devices',
    'preferences',
    'macros',
    'actions_log',
    'events',
    'profile_meta',
    'reflection_records',
    'site_memory',
    'preference_memory',
    'workflow_memory',
    'safety_memory',
    'run_records',
    'run_events',
    'approval_records',
    'audit_log',
    'context_snapshots',
]

def export_profile(path: str) -> str:
    conn = get_conn()
    data = {}
    for table in PROFILE_TABLES:
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
