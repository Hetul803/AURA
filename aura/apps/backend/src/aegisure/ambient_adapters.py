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


def adapter_contracts() -> list[dict[str, Any]]:
    return [
        {
            'adapter_id': 'home-assistant',
            'surface': 'home',
            'status': 'planned_contract',
            'capabilities': ['household_routines', 'smart_home_action_later', 'family_boundary_later'],
            'allowed_without_approval': ['read_room_state', 'reminder', 'routine_summary'],
            'requires_approval': ['unlock_door', 'change_security_mode', 'turn_off_alarm', 'control_appliance'],
            'blocked': ['disable_safety_device_without_user_present'],
        },
        {
            'adapter_id': 'car-assistant',
            'surface': 'car',
            'status': 'planned_contract',
            'capabilities': ['voice_first', 'navigation_context_later', 'message_draft_later', 'handoff_to_phone_or_desktop'],
            'allowed_without_approval': ['read_calendar_summary', 'navigation_summary', 'create_deferred_reminder'],
            'requires_approval': ['send_message', 'start_call', 'change_navigation_destination'],
            'blocked': ['long_form_visual_task_while_driving', 'complex_form_fill_while_driving', 'code_editing_while_driving'],
        },
    ]


def classify_ambient_action(*, surface: str, action: str, driving: bool = False) -> dict[str, Any]:
    low = action.lower().strip()
    if surface == 'car' and driving and any(token in low for token in ['code', 'form', 'read long', 'browse']):
        return {'decision': 'defer', 'safety_class': 'driving_limited', 'approval_required': False, 'reason': 'Complex visual or cognitive work should be handed off while driving.'}
    if surface == 'car' and any(token in low for token in ['send', 'call', 'message']):
        return {'decision': 'require_approval', 'safety_class': 'communication', 'approval_required': True, 'reason': 'Car communication actions require explicit voice approval.'}
    if surface == 'home' and any(token in low for token in ['unlock', 'alarm', 'security', 'door']):
        return {'decision': 'require_approval', 'safety_class': 'home_security', 'approval_required': True, 'reason': 'Home security actions require confirmation.'}
    if surface == 'home' and any(token in low for token in ['remind', 'routine', 'summary']):
        return {'decision': 'allow', 'safety_class': 'household_low_risk', 'approval_required': False, 'reason': 'Low-risk household routine.'}
    return {'decision': 'require_approval', 'safety_class': f'{surface}_default_cautious', 'approval_required': True, 'reason': 'Unknown ambient action requires approval.'}


def _routine_row(row) -> dict[str, Any]:
    data = dict(row)
    data['approval_required'] = bool(data.get('approval_required'))
    data['enabled'] = bool(data.get('enabled'))
    data['metadata'] = _loads(data.pop('metadata_json', None))
    return data


def create_ambient_routine(
    *,
    surface: str,
    name: str,
    trigger_value: str,
    action_summary: str,
    enabled: bool = False,
    metadata: dict[str, Any] | None = None,
    routine_id: str | None = None,
) -> dict[str, Any]:
    classification = classify_ambient_action(surface=surface, action=action_summary, driving=bool((metadata or {}).get('driving')))
    rid = routine_id or f'ambient_{uuid.uuid4().hex}'
    now = _now()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO ambient_routines(
              routine_id, surface, name, trigger_value, action_summary, safety_class,
              approval_required, enabled, metadata_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                rid,
                surface,
                name,
                trigger_value,
                action_summary,
                classification['safety_class'],
                1 if classification['approval_required'] else 0,
                1 if enabled else 0,
                json.dumps({**(metadata or {}), 'classification': classification}, sort_keys=True),
                now,
                now,
            ),
        )
    return get_ambient_routine(rid) or {'routine_id': rid}


def get_ambient_routine(routine_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM ambient_routines WHERE routine_id=?', (routine_id,)).fetchone()
    return _routine_row(row) if row else None


def list_ambient_routines(surface: str | None = None, include_disabled: bool = False) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if surface:
        clauses.append('surface=?')
        params.append(surface)
    if not include_disabled:
        clauses.append('enabled=1')
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = db_conn().execute(f'SELECT * FROM ambient_routines {where} ORDER BY created_at DESC', params).fetchall()
    return [_routine_row(row) for row in rows]
