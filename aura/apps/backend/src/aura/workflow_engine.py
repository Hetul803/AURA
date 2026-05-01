from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .agent_router import workflow_suggestions
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
    data['enabled'] = bool(data.get('enabled'))
    data['metadata'] = _loads(data.pop('metadata_json', None))
    return data


def create_workflow(
    *,
    name: str,
    command_template: str,
    description: str = '',
    trigger_type: str = 'manual',
    trigger_value: str = '',
    enabled: bool = True,
    approval_policy: str = 'ask_for_risky_actions',
    source: str = 'manual',
    confidence: float = 0.5,
    metadata: dict[str, Any] | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    wid = workflow_id or f'wf_{uuid.uuid4().hex}'
    now = _now()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO workflow_templates(
              workflow_id, name, description, trigger_type, trigger_value, command_template,
              enabled, approval_policy, source, confidence, metadata_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                wid,
                name,
                description,
                trigger_type,
                trigger_value,
                command_template,
                1 if enabled else 0,
                approval_policy,
                source,
                confidence,
                json.dumps(metadata or {}, sort_keys=True),
                now,
                now,
            ),
        )
    return get_workflow(wid) or {'workflow_id': wid}


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM workflow_templates WHERE workflow_id=?', (workflow_id,)).fetchone()
    return _row(row) if row else None


def list_workflows(*, include_disabled: bool = False, trigger_type: str | None = None) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if not include_disabled:
        clauses.append('enabled=1')
    if trigger_type:
        clauses.append('trigger_type=?')
        params.append(trigger_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = db_conn().execute(
        f'SELECT * FROM workflow_templates {where} ORDER BY confidence DESC, updated_at DESC',
        params,
    ).fetchall()
    return [_row(row) for row in rows]


def update_workflow(workflow_id: str, **changes: Any) -> dict[str, Any] | None:
    allowed = {'name', 'description', 'trigger_type', 'trigger_value', 'command_template', 'approval_policy', 'source', 'confidence'}
    fields = []
    params: list[Any] = []
    for key, value in changes.items():
        if value is None:
            continue
        if key == 'metadata':
            fields.append('metadata_json=?')
            params.append(json.dumps(value or {}, sort_keys=True))
        elif key == 'enabled':
            fields.append('enabled=?')
            params.append(1 if value else 0)
        elif key in allowed:
            fields.append(f'{key}=?')
            params.append(value)
    if not fields:
        return get_workflow(workflow_id)
    fields.append('updated_at=?')
    params.append(_now())
    params.append(workflow_id)
    with db_conn() as conn:
        cur = conn.execute(f"UPDATE workflow_templates SET {', '.join(fields)} WHERE workflow_id=?", params)
        if cur.rowcount == 0:
            return None
    return get_workflow(workflow_id)


def delete_workflow(workflow_id: str) -> bool:
    with db_conn() as conn:
        cur = conn.execute('DELETE FROM workflow_templates WHERE workflow_id=?', (workflow_id,))
        return cur.rowcount > 0


def render_workflow_command(workflow_id: str, variables: dict[str, Any] | None = None) -> dict[str, Any] | None:
    workflow = get_workflow(workflow_id)
    if not workflow:
        return None
    command = workflow['command_template']
    for key, value in (variables or {}).items():
        command = command.replace('{' + key + '}', str(value))
    return {'workflow': workflow, 'command': command, 'variables': variables or {}}


def suggested_workflow_templates(limit: int = 10) -> list[dict[str, Any]]:
    out = []
    for item in workflow_suggestions(limit=limit):
        task_type = item.get('task_type') or 'generic'
        pattern_key = item.get('pattern_key') or 'pattern'
        name = f"{task_type}: {pattern_key}"
        command_template = _command_for_suggestion(item)
        out.append({
            **item,
            'name': name,
            'description': f"Suggested from AURA learning: {item.get('strategy')}",
            'trigger_type': 'manual',
            'trigger_value': pattern_key,
            'command_template': command_template,
            'approval_policy': 'ask_for_risky_actions',
            'source': 'learning_suggestion',
        })
    return out


def _command_for_suggestion(item: dict[str, Any]) -> str:
    task_type = item.get('task_type') or ''
    pattern = item.get('pattern_key') or ''
    if task_type == 'agent:coding':
        return 'Create a full app for this idea'
    if task_type == 'assist:writing' and pattern.startswith('task_kind:reply'):
        return 'Draft a reply to this'
    if task_type == 'assist:writing':
        return 'Summarize this'
    if task_type == 'github:clone':
        return 'Clone this repo locally'
    return task_type.replace(':', ' ') or 'Summarize this'
