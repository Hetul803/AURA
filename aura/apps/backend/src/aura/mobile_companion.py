from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from .device_handoff import create_handoff, list_handoffs, update_handoff
from .state import db_conn, get_run_context, list_run_events


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _row(row) -> dict[str, Any]:
    data = dict(row)
    data['capabilities'] = _loads(data.pop('capabilities_json', None), [])
    data['metadata'] = _loads(data.pop('metadata_json', None), {})
    return data


def create_pairing_code() -> dict[str, Any]:
    return {
        'pairing_code': secrets.token_hex(3).upper(),
        'expires_hint': 'single_use_private_alpha',
        'instructions': 'Enter this code in the future AURA mobile companion while on a trusted device.',
    }


def register_mobile_device(
    *,
    device_name: str,
    pairing_code: str,
    capabilities: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    did = device_id or f'mobile_{uuid.uuid4().hex}'
    now = _now()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO mobile_devices(device_id, device_name, pairing_code, status, capabilities_json, metadata_json, created_at, last_seen)
            VALUES(?,?,?,?,?,?,?,?)
            ''',
            (
                did,
                device_name,
                pairing_code,
                'paired',
                json.dumps(capabilities or ['approval_inbox', 'run_status', 'command_handoff'], sort_keys=True),
                json.dumps(metadata or {}, sort_keys=True),
                now,
                now,
            ),
        )
    return get_mobile_device(did) or {'device_id': did}


def get_mobile_device(device_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM mobile_devices WHERE device_id=?', (device_id,)).fetchone()
    return _row(row) if row else None


def list_mobile_devices() -> list[dict[str, Any]]:
    rows = db_conn().execute('SELECT * FROM mobile_devices ORDER BY last_seen DESC').fetchall()
    return [_row(row) for row in rows]


def mark_mobile_seen(device_id: str) -> dict[str, Any] | None:
    with db_conn() as conn:
        cur = conn.execute('UPDATE mobile_devices SET last_seen=? WHERE device_id=?', (_now(), device_id))
        if cur.rowcount == 0:
            return None
    return get_mobile_device(device_id)


def mobile_status(device_id: str | None = None) -> dict[str, Any]:
    if device_id:
        mark_mobile_seen(device_id)
    pending = list_handoffs(status='pending', target_device='phone-companion')
    return {
        'device_id': device_id,
        'paired_devices': list_mobile_devices(),
        'pending_handoffs': len(pending),
        'capabilities': ['approval_inbox', 'run_status', 'command_handoff'],
    }


def mobile_inbox(device_id: str | None = None) -> list[dict[str, Any]]:
    if device_id:
        mark_mobile_seen(device_id)
    return list_handoffs(target_device='phone-companion', limit=50)


def create_mobile_approval_card(*, run_id: str, title: str, body: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return create_handoff(
        source_device='desktop-local',
        target_device='phone-companion',
        run_id=run_id,
        approval_required=True,
        payload={'type': 'approval_card', 'title': title, 'body': body, 'action': action, 'payload': payload or {}},
    )


def mobile_run_summary(run_id: str) -> dict[str, Any]:
    state = get_run_context(run_id) or {}
    return {
        'run_id': run_id,
        'status': state.get('status'),
        'terminal_outcome': state.get('terminal_outcome'),
        'goal': ((state.get('plan') or {}).get('goal')),
        'events': list_run_events(run_id)[-20:],
        'approval_state': state.get('approval_state') or {},
    }


def decide_mobile_handoff(handoff_id: str, decision: str) -> dict[str, Any] | None:
    status = 'approved' if decision == 'approve' else 'rejected'
    handoff = update_handoff(handoff_id, status=status)
    if not handoff:
        return None
    return handoff
