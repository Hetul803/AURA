from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .state import db_conn


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


DEFAULT_USAGE_LIMITS = {
    'monthly_agent_runs': 100,
    'monthly_cloud_llm_usd': 0.0,
    'memory_items': 5000,
}


def _row(row) -> dict[str, Any]:
    data = dict(row)
    data['cloud_sync_enabled'] = bool(data.get('cloud_sync_enabled'))
    data['usage_limits'] = _loads(data.pop('usage_limits_json', None), {})
    data['model_cost_limits'] = _loads(data.pop('model_cost_limits_json', None), {})
    data['cloud_storage_target'] = _loads(data.pop('cloud_storage_target_json', None), {})
    data['metadata'] = _loads(data.pop('metadata_json', None), {})
    return data


def ensure_local_profile() -> dict[str, Any]:
    row = db_conn().execute('SELECT * FROM local_profile_account ORDER BY created_at LIMIT 1').fetchone()
    if row:
        return _row(row)
    profile_id = f'profile_{uuid.uuid4().hex}'
    now = _now()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO local_profile_account(
              profile_id, display_name, local_user_id, subscription_tier, trial_state, billing_status,
              usage_limits_json, model_cost_limits_json, device_limit, cloud_sync_enabled,
              memory_sync_identity, cloud_storage_target_json, metadata_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                profile_id,
                'Local AURA User',
                f'local_{uuid.uuid4().hex}',
                'local_free',
                'not_started',
                'local_only',
                json.dumps(DEFAULT_USAGE_LIMITS, sort_keys=True),
                json.dumps({'monthly_cloud_llm_usd': 0.0}, sort_keys=True),
                1,
                0,
                'local_only',
                json.dumps({'provider': 'none', 'encrypted_backup_enabled': False}, sort_keys=True),
                json.dumps({'local_first': True, 'payments_configured': False}, sort_keys=True),
                now,
                now,
            ),
        )
    return get_profile_status(profile_id) or {'profile_id': profile_id}


def get_profile_status(profile_id: str | None = None) -> dict[str, Any] | None:
    if profile_id:
        row = db_conn().execute('SELECT * FROM local_profile_account WHERE profile_id=?', (profile_id,)).fetchone()
    else:
        row = db_conn().execute('SELECT * FROM local_profile_account ORDER BY created_at LIMIT 1').fetchone()
    return _row(row) if row else None


def update_profile_status(**changes: Any) -> dict[str, Any]:
    profile = ensure_local_profile()
    allowed = {
        'display_name',
        'cloud_account_id',
        'subscription_tier',
        'trial_state',
        'billing_status',
        'device_limit',
        'memory_sync_identity',
    }
    fields = []
    params: list[Any] = []
    for key, value in changes.items():
        if value is None:
            continue
        if key in {'usage_limits', 'model_cost_limits', 'cloud_storage_target', 'metadata'}:
            fields.append(f'{key}_json=?')
            params.append(json.dumps(value or {}, sort_keys=True))
        elif key == 'cloud_sync_enabled':
            fields.append('cloud_sync_enabled=?')
            params.append(1 if value else 0)
        elif key in allowed:
            fields.append(f'{key}=?')
            params.append(value)
    if not fields:
        return profile
    fields.append('updated_at=?')
    params.append(_now())
    params.append(profile['profile_id'])
    with db_conn() as conn:
        conn.execute(f"UPDATE local_profile_account SET {', '.join(fields)} WHERE profile_id=?", params)
    return get_profile_status(profile['profile_id']) or profile
