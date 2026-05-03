from __future__ import annotations
import json
from pathlib import Path
from aura.privacy import detect_secret, redact_value
from .db import get_conn
from .profile_paths import profile_dir

PROFILE_TABLES = [
    'memories',
    'memory_items',
    'model_usage_events',
    'model_response_cache',
    'cost_budgets',
    'workflow_templates',
    'workflow_versions',
    'workflow_repair_records',
    'local_profile_account',
    'device_handoffs',
    'aura_identities',
    'boundary_policies',
    'mobile_devices',
    'ambient_routines',
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

def _safe_bundle_path(path: str) -> Path:
    target = Path(path).expanduser()
    if '..' in target.parts:
        raise ValueError('path_traversal_blocked')
    if not target.is_absolute():
        target = profile_dir() / 'exports' / target
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def export_profile(path: str) -> str:
    conn = get_conn()
    data = {}
    for table in PROFILE_TABLES:
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
        data[table] = redact_value(rows)
    target = _safe_bundle_path(path)
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(target)

def import_profile(path: str) -> None:
    conn = get_conn()
    target = _safe_bundle_path(path)
    raw = target.read_text(encoding="utf-8")
    if detect_secret(raw):
        raise ValueError('profile_import_contains_secret')
    data = json.loads(raw)
    with conn:
        for table, rows in data.items():
            if table not in PROFILE_TABLES:
                continue
            conn.execute(f"DELETE FROM {table}")
            for row in rows:
                keys = list(row.keys())
                vals = [row[k] for k in keys]
                q = ",".join("?" for _ in keys)
                conn.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({q})", vals)
