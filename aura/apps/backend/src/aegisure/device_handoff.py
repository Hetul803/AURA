from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .state import db_conn


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _row(row) -> dict[str, Any]:
    data = dict(row)
    data['approval_required'] = bool(data.get('approval_required'))
    data['payload'] = _loads(data.pop('payload_json', None))
    return data


def create_handoff(
    *,
    source_device: str,
    target_device: str,
    payload: dict[str, Any],
    run_id: str | None = None,
    approval_required: bool = False,
    status: str = 'pending',
    handoff_id: str | None = None,
) -> dict[str, Any]:
    hid = handoff_id or f'handoff_{uuid.uuid4().hex}'
    now = _now()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO device_handoffs(
              handoff_id, source_device, target_device, run_id, status, approval_required, payload_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ''',
            (hid, source_device, target_device, run_id, status, 1 if approval_required else 0, json.dumps(payload, sort_keys=True), now, now),
        )
    return get_handoff(hid) or {'handoff_id': hid}


def get_handoff(handoff_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM device_handoffs WHERE handoff_id=?', (handoff_id,)).fetchone()
    return _row(row) if row else None


def list_handoffs(*, status: str | None = None, target_device: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append('status=?')
        params.append(status)
    if target_device:
        clauses.append('target_device=?')
        params.append(target_device)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = db_conn().execute(
        f'SELECT * FROM device_handoffs {where} ORDER BY created_at DESC LIMIT ?',
        [*params, limit],
    ).fetchall()
    return [_row(row) for row in rows]


def update_handoff(handoff_id: str, *, status: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    fields = []
    params: list[Any] = []
    if status is not None:
        fields.append('status=?')
        params.append(status)
    if payload is not None:
        fields.append('payload_json=?')
        params.append(json.dumps(payload, sort_keys=True))
    if not fields:
        return get_handoff(handoff_id)
    fields.append('updated_at=?')
    params.append(_now())
    params.append(handoff_id)
    with db_conn() as conn:
        cur = conn.execute(f"UPDATE device_handoffs SET {', '.join(fields)} WHERE handoff_id=?", params)
        if cur.rowcount == 0:
            return None
    return get_handoff(handoff_id)
