from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from storage.db import get_conn
from .privacy import redact_value, safe_json_dumps

PANIC = False
RUN_CANCEL: dict[str, bool] = defaultdict(bool)
RUN_CONTEXT: dict[str, dict] = {}
SAFETY_EVENTS: list[dict] = []
GUARDIAN_EVENTS: list[dict] = []
LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _json_dumps(value) -> str:
    return safe_json_dumps(value)


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback



def db_conn():
    return get_conn()



def set_panic(v: bool):
    global PANIC
    PANIC = v



def is_panic() -> bool:
    return PANIC



def cancel_run(run_id: str):
    with LOCK:
        RUN_CANCEL[run_id] = True



def is_run_cancelled(run_id: str) -> bool:
    with LOCK:
        return RUN_CANCEL.get(run_id, False) or PANIC



def set_run_context(run_id: str, context: dict):
    with LOCK:
        RUN_CONTEXT[run_id] = context
    persist_run_context(run_id, context)



def update_run_context(run_id: str, patch: dict):
    with LOCK:
        current = RUN_CONTEXT.get(run_id, {})
        RUN_CONTEXT[run_id] = {**current, **patch}
        updated = RUN_CONTEXT[run_id]
    persist_run_context(run_id, updated)
    return updated



def append_run_history(run_id: str, key: str, item: dict, limit: int = 20):
    with LOCK:
        current = RUN_CONTEXT.get(run_id, {})
        history = list(current.get(key, []))
        history.append(item)
        RUN_CONTEXT[run_id] = {**current, key: history[-limit:]}
        updated = RUN_CONTEXT[run_id]
    persist_run_context(run_id, updated)
    return updated[key]



def increment_run_counter(run_id: str, key: str, amount: int = 1):
    with LOCK:
        current = RUN_CONTEXT.get(run_id, {})
        current_value = int(current.get(key, 0))
        RUN_CONTEXT[run_id] = {**current, key: current_value + amount}
        updated = RUN_CONTEXT[run_id]
    persist_run_context(run_id, updated)
    return updated[key]



def get_run_context(run_id: str) -> dict | None:
    with LOCK:
        cached = RUN_CONTEXT.get(run_id)
    if cached is not None:
        return cached
    row = get_conn().execute('SELECT context_json FROM run_records WHERE run_id=?', (run_id,)).fetchone()
    if not row:
        return None
    context = _json_loads(row['context_json'], {})
    with LOCK:
        RUN_CONTEXT[run_id] = context
    return context



def list_runs() -> dict[str, dict]:
    with LOCK:
        return dict(RUN_CONTEXT)



def record_safety_event(evt: dict):
    with LOCK:
        SAFETY_EVENTS.append(evt)
        del SAFETY_EVENTS[:-200]
    record_audit_event({
        'run_id': evt.get('run_id'),
        'step_id': evt.get('step_id'),
        'event_type': f"safety_{evt.get('kind', 'event')}",
        'action_type': evt.get('action'),
        'risk_level': evt.get('risk_level') or evt.get('safety_level'),
        'message': evt.get('message') or evt.get('kind'),
        'payload': evt,
    })



def list_safety_events() -> list[dict]:
    with LOCK:
        return list(SAFETY_EVENTS)


def persist_run_context(run_id: str, context: dict):
    text = str(redact_value(context.get('text') or ''))
    status = str(context.get('status') or '')
    payload = _json_dumps(redact_value(context))
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO run_records(run_id, text, status, context_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              text=excluded.text,
              status=excluded.status,
              context_json=excluded.context_json,
              updated_at=excluded.updated_at
            """,
            (run_id, text, status, payload, now, now),
        )


def record_run_event(evt: dict):
    run_id = evt.get('run_id')
    if not run_id:
        return
    evt = redact_value(evt)
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO run_events(run_id,event_type,status,step_id,payload_json) VALUES(?,?,?,?,?)',
            (
                run_id,
                evt.get('type') or evt.get('event_type') or evt.get('status'),
                evt.get('status'),
                evt.get('step_id'),
                _json_dumps(evt),
            ),
        )


def list_run_events(run_id: str) -> list[dict]:
    rows = get_conn().execute(
        'SELECT * FROM run_events WHERE run_id=? ORDER BY id',
        (run_id,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item['payload'] = _json_loads(item.pop('payload_json', None), {})
        out.append(item)
    return out


def record_audit_event(event: dict):
    event = redact_value(event)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO audit_log(run_id,step_id,event_type,action_type,risk_level,message,payload_json)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                event.get('run_id'),
                event.get('step_id'),
                event.get('event_type'),
                event.get('action_type'),
                event.get('risk_level'),
                event.get('message'),
                _json_dumps(event.get('payload') or event),
            ),
        )


def list_audit_log(run_id: str | None = None, limit: int = 100) -> list[dict]:
    if run_id:
        rows = get_conn().execute(
            'SELECT * FROM audit_log WHERE run_id=? ORDER BY id DESC LIMIT ?',
            (run_id, limit),
        ).fetchall()
    else:
        rows = get_conn().execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item['payload'] = _json_loads(item.pop('payload_json', None), {})
        out.append(item)
    return out


def create_approval_request(run_id: str, step, risk_reason: str) -> dict:
    existing = pending_approval(run_id)
    if existing and existing.get('step_id') == step.id:
        return existing
    approval_id = str(uuid4())
    payload = redact_value({
        'approval_id': approval_id,
        'run_id': run_id,
        'step_id': step.id,
        'step_name': step.name,
        'action_type': step.action_type,
        'tool': step.tool,
        'args': step.args,
        'safety_level': step.safety_level,
        'risk_reason': risk_reason,
    })
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO approval_records(
              approval_id, run_id, step_id, action_type, risk_reason, status, requested_payload_json, requested_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (approval_id, run_id, step.id, step.action_type, risk_reason, _json_dumps(payload), now),
        )
    record_audit_event({
        'run_id': run_id,
        'step_id': step.id,
        'event_type': 'approval_requested',
        'action_type': step.action_type,
        'risk_level': step.safety_level,
        'message': risk_reason,
        'payload': payload,
    })
    return {**payload, 'status': 'pending', 'requested_at': now}


def pending_approval(run_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM approval_records WHERE run_id=? AND status='pending' ORDER BY requested_at DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    payload = _json_loads(item.get('requested_payload_json'), {})
    return {**payload, 'status': item['status'], 'requested_at': item['requested_at']}


def decide_approval(run_id: str, approved: bool, decision: dict | None = None) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM approval_records WHERE run_id=? AND status='pending' ORDER BY requested_at DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    if not row:
        return None
    status = 'approved' if approved else 'rejected'
    decision_payload = decision or {}
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            'UPDATE approval_records SET status=?, decision_payload_json=?, decided_at=? WHERE approval_id=?',
            (status, _json_dumps(decision_payload), now, row['approval_id']),
        )
    requested = _json_loads(row['requested_payload_json'], {})
    record_audit_event({
        'run_id': run_id,
        'step_id': row['step_id'],
        'event_type': f'approval_{status}',
        'action_type': row['action_type'],
        'risk_level': requested.get('safety_level'),
        'message': decision_payload.get('reason') or status,
        'payload': {'approval_id': row['approval_id'], **decision_payload},
    })
    return {**requested, 'status': status, 'decided_at': now, 'decision': decision_payload}


def is_step_approved(run_id: str, step_id: str) -> bool:
    row = get_conn().execute(
        """
        SELECT status FROM approval_records
        WHERE run_id=? AND step_id=? AND status='approved'
        ORDER BY decided_at DESC LIMIT 1
        """,
        (run_id, step_id),
    ).fetchone()
    return bool(row)


def record_guardian_event(evt: dict):
    evt = redact_value(evt)
    with LOCK:
        GUARDIAN_EVENTS.append(evt)
        del GUARDIAN_EVENTS[:-300]
    record_audit_event({
        'run_id': evt.get('run_id'),
        'step_id': evt.get('step_id'),
        'event_type': f"guardian_{evt.get('type', 'event')}",
        'action_type': evt.get('action'),
        'risk_level': evt.get('risk'),
        'message': evt.get('summary'),
        'payload': evt,
    })


def list_guardian_events(run_id: str | None = None, limit: int = 100) -> list[dict]:
    with LOCK:
        items = list(GUARDIAN_EVENTS)
    if run_id:
        items = [item for item in items if item.get('run_id') == run_id]
    return items[-limit:][::-1]
