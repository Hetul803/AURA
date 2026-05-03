from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .agent_router import workflow_suggestions
from .privacy import detect_secret, redact_value
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


def _loads_list(value: str | None) -> list[Any]:
    loaded = _loads(value)
    return loaded if isinstance(loaded, list) else []


def _row(row) -> dict[str, Any]:
    data = dict(row)
    data['enabled'] = bool(data.get('enabled'))
    data['metadata'] = _loads(data.pop('metadata_json', None))
    data['required_context'] = _loads_list(data.pop('required_context_json', None))
    return data


def _version_row(row) -> dict[str, Any]:
    data = dict(row)
    data['archived'] = bool(data.get('archived'))
    data['steps'] = _loads_list(data.pop('steps_json', None))
    data['required_context'] = _loads_list(data.pop('required_context_json', None))
    data['approval_requirements'] = _loads_list(data.pop('approval_requirements_json', None))
    data['linked_memories'] = _loads_list(data.pop('linked_memories_json', None))
    return data


def _repair_row(row) -> dict[str, Any]:
    data = dict(row)
    data['repair_succeeded'] = bool(data.get('repair_succeeded'))
    data['update_recommended'] = bool(data.get('update_recommended'))
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
    required_context: list[str] | None = None,
    safety_class: str = 'medium',
    repair_strategy: str = 'retry_then_escalate',
    linked_memories: list[str] | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    wid = workflow_id or f'wf_{uuid.uuid4().hex}'
    now = _now()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO workflow_templates(
              workflow_id, name, description, trigger_type, trigger_value, command_template,
              required_context_json, safety_class, repair_strategy, active_version,
              enabled, approval_policy, source, confidence, metadata_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                wid,
                name,
                description,
                trigger_type,
                trigger_value,
                command_template,
                json.dumps(required_context or [], sort_keys=True),
                safety_class,
                repair_strategy,
                1,
                1 if enabled else 0,
                approval_policy,
                source,
                confidence,
                json.dumps(metadata or {}, sort_keys=True),
                now,
                now,
            ),
        )
        conn.execute(
            '''
            INSERT OR IGNORE INTO workflow_versions(
              version_id, workflow_id, version, command_template, required_context_json,
              approval_requirements_json, safety_class, repair_strategy, linked_memories_json, changelog, archived, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                f'wfv_{uuid.uuid4().hex}',
                wid,
                1,
                command_template,
                json.dumps(required_context or [], sort_keys=True),
                json.dumps([approval_policy], sort_keys=True),
                safety_class,
                repair_strategy,
                json.dumps(linked_memories or [], sort_keys=True),
                'Initial workflow version',
                0,
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
    before = get_workflow(workflow_id)
    allowed = {'name', 'description', 'trigger_type', 'trigger_value', 'command_template', 'approval_policy', 'source', 'confidence', 'safety_class', 'repair_strategy'}
    fields = []
    params: list[Any] = []
    for key, value in changes.items():
        if value is None:
            continue
        if key == 'metadata':
            fields.append('metadata_json=?')
            params.append(json.dumps(value or {}, sort_keys=True))
        elif key == 'required_context':
            fields.append('required_context_json=?')
            params.append(json.dumps(value or [], sort_keys=True))
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
    updated = get_workflow(workflow_id)
    if before and updated and any(key in changes for key in {'command_template', 'required_context', 'approval_policy', 'safety_class', 'repair_strategy'}):
        create_workflow_version(
            workflow_id,
            command_template=updated['command_template'],
            required_context=updated.get('required_context') or [],
            approval_requirements=[updated.get('approval_policy')],
            safety_class=updated.get('safety_class') or 'medium',
            repair_strategy=updated.get('repair_strategy') or 'retry_then_escalate',
            changelog=changes.get('changelog') or 'Workflow template updated',
        )
        return get_workflow(workflow_id)
    return updated


def delete_workflow(workflow_id: str) -> bool:
    with db_conn() as conn:
        cur = conn.execute('DELETE FROM workflow_templates WHERE workflow_id=?', (workflow_id,))
        return cur.rowcount > 0


def render_workflow_command(workflow_id: str, variables: dict[str, Any] | None = None) -> dict[str, Any] | None:
    workflow = get_workflow(workflow_id)
    if not workflow:
        return None
    command = workflow['command_template']
    for key, value in redact_value(variables or {}).items():
        command = command.replace('{' + key + '}', str(value))
    return {'workflow': workflow, 'command': command, 'variables': variables or {}}


def validate_workflow_run(workflow: dict[str, Any], *, command: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    missing = []
    for requirement in workflow.get('required_context') or []:
        if requirement == 'browser_url:github_repo' and not any(ref.get('type') == 'github_repo' for ref in context.get('context_refs', [])):
            missing.append(requirement)
        elif requirement == 'selected_text_or_clipboard' and not (context.get('selected_text') or context.get('input_text') or context.get('clipboard_text')):
            missing.append(requirement)
        elif requirement == 'active_app_target' and not (context.get('active_app') or context.get('window_title')):
            missing.append(requirement)
        elif requirement == 'workspace_or_repo' and not (context.get('workspace_hint') or context.get('current_repo') or context.get('project')):
            missing.append(requirement)
    if detect_secret(command) or detect_secret(json.dumps(context, default=str)):
        return {'ok': False, 'blocked': True, 'reason': 'workflow_contains_secret_or_sensitive_input', 'missing_context': missing}
    if missing:
        return {'ok': False, 'blocked': False, 'reason': 'missing_required_context', 'missing_context': missing}
    risky = workflow.get('safety_class') in {'high', 'critical'} or workflow.get('approval_policy') in {'always_ask', 'require_approval'}
    return {'ok': True, 'blocked': False, 'requires_approval': risky, 'reason': 'workflow_preflight_passed', 'missing_context': []}


def create_workflow_version(
    workflow_id: str,
    *,
    command_template: str,
    steps: list[dict[str, Any]] | None = None,
    required_context: list[str] | None = None,
    approval_requirements: list[str] | None = None,
    safety_class: str = 'medium',
    repair_strategy: str = 'retry_then_escalate',
    linked_memories: list[str] | None = None,
    changelog: str = '',
) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise KeyError(workflow_id)
    current = int(workflow.get('active_version') or 1)
    next_version = current + 1
    now = _now()
    with db_conn() as conn:
        conn.execute('UPDATE workflow_versions SET archived=1 WHERE workflow_id=? AND archived=0', (workflow_id,))
        conn.execute(
            '''
            INSERT INTO workflow_versions(
              version_id, workflow_id, version, command_template, steps_json, required_context_json,
              approval_requirements_json, safety_class, repair_strategy, linked_memories_json, changelog, archived, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                f'wfv_{uuid.uuid4().hex}',
                workflow_id,
                next_version,
                command_template,
                json.dumps(steps or [], sort_keys=True),
                json.dumps(required_context or [], sort_keys=True),
                json.dumps(approval_requirements or [], sort_keys=True),
                safety_class,
                repair_strategy,
                json.dumps(linked_memories or [], sort_keys=True),
                changelog,
                0,
                now,
            ),
        )
        conn.execute(
            'UPDATE workflow_templates SET active_version=?, command_template=?, required_context_json=?, safety_class=?, repair_strategy=?, updated_at=? WHERE workflow_id=?',
            (next_version, command_template, json.dumps(required_context or [], sort_keys=True), safety_class, repair_strategy, now, workflow_id),
        )
    return list_workflow_versions(workflow_id)[0]


def list_workflow_versions(workflow_id: str) -> list[dict[str, Any]]:
    rows = db_conn().execute('SELECT * FROM workflow_versions WHERE workflow_id=? ORDER BY version DESC', (workflow_id,)).fetchall()
    return [_version_row(row) for row in rows]


def record_workflow_result(workflow_id: str, *, ok: bool, failure_reason: str | None = None, version: int | None = None) -> dict[str, Any] | None:
    workflow = get_workflow(workflow_id)
    if not workflow:
        return None
    version = version or int(workflow.get('active_version') or 1)
    field = 'success_count' if ok else 'failure_count'
    with db_conn() as conn:
        conn.execute(
            f'UPDATE workflow_templates SET {field}=COALESCE({field},0)+1, last_failure_reason=?, updated_at=? WHERE workflow_id=?',
            (None if ok else failure_reason, _now(), workflow_id),
        )
        conn.execute(
            f'UPDATE workflow_versions SET {field}=COALESCE({field},0)+1, last_failure_reason=? WHERE workflow_id=? AND version=?',
            (None if ok else failure_reason, workflow_id, version),
        )
    return get_workflow(workflow_id)


def record_workflow_repair(
    workflow_id: str,
    *,
    run_id: str | None = None,
    version: int | None = None,
    failed_step: str = '',
    failure_reason: str = '',
    repair_summary: str = '',
    repair_succeeded: bool = False,
    update_recommended: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise KeyError(workflow_id)
    version = version or int(workflow.get('active_version') or 1)
    recent_failures = int(workflow.get('failure_count') or 0) + (0 if repair_succeeded else 1)
    should_update = update_recommended if update_recommended is not None else recent_failures >= 2
    repair_id = f'wfr_{uuid.uuid4().hex}'
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO workflow_repair_records(
              repair_id, workflow_id, version, run_id, failed_step, failure_reason, repair_summary,
              repair_succeeded, update_recommended, metadata_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                repair_id,
                workflow_id,
                version,
                run_id,
                failed_step,
                failure_reason,
                repair_summary,
                1 if repair_succeeded else 0,
                1 if should_update else 0,
                json.dumps(metadata or {}, sort_keys=True),
                _now(),
            ),
        )
    record_workflow_result(workflow_id, ok=repair_succeeded, failure_reason=None if repair_succeeded else failure_reason, version=version)
    return get_workflow_repair(repair_id) or {'repair_id': repair_id}


def get_workflow_repair(repair_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM workflow_repair_records WHERE repair_id=?', (repair_id,)).fetchone()
    return _repair_row(row) if row else None


def list_workflow_repairs(workflow_id: str) -> list[dict[str, Any]]:
    rows = db_conn().execute('SELECT * FROM workflow_repair_records WHERE workflow_id=? ORDER BY created_at DESC', (workflow_id,)).fetchall()
    return [_repair_row(row) for row in rows]


def workflow_update_suggestions(workflow_id: str) -> list[dict[str, Any]]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        return []
    repairs = list_workflow_repairs(workflow_id)
    failure_count = int(workflow.get('failure_count') or 0)
    suggestions = []
    if failure_count >= 2 or any(r.get('update_recommended') for r in repairs[:3]):
        last = repairs[0] if repairs else {}
        suggestions.append({
            'workflow_id': workflow_id,
            'active_version': workflow.get('active_version'),
            'suggestion': 'create_revised_version',
            'reason': last.get('failure_reason') or workflow.get('last_failure_reason') or 'repeated_failures',
            'repair_strategy': workflow.get('repair_strategy') or 'retry_then_escalate',
            'proposed_changelog': f"Revise workflow after failure: {last.get('failure_reason') or 'repeated failure'}",
        })
    return suggestions


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
            'required_context': _required_context_for(task_type),
            'safety_class': _safety_class_for(task_type),
            'repair_strategy': 'retry_then_escalate',
            'source': 'learning_suggestion',
        })
    return out


def _required_context_for(task_type: str) -> list[str]:
    if task_type == 'github:clone':
        return ['browser_url:github_repo']
    if task_type == 'assist:writing':
        return ['selected_text_or_clipboard', 'active_app_target']
    if task_type == 'agent:coding':
        return ['workspace_or_repo']
    return []


def _safety_class_for(task_type: str) -> str:
    if task_type in {'github:clone', 'agent:coding'}:
        return 'high'
    if task_type == 'assist:writing':
        return 'medium'
    return 'low'


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
