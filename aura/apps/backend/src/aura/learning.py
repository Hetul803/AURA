from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from storage.db import get_conn


REFLECTION_LIMIT = 200
RELEVANT_MEMORY_LIMIT = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _json_dumps(value) -> str:
    return json.dumps(value, sort_keys=True)


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc or None


def _domain_from_context(ctx: dict) -> str | None:
    plan = ctx.get('plan') or {}
    last_observation = ctx.get('last_observation') or {}
    domain = _domain_from_url(last_observation.get('url'))
    if domain:
        return domain
    for step in plan.get('steps', []):
        url = (step.get('args') or {}).get('url')
        domain = _domain_from_url(url)
        if domain:
            return domain
    signature = plan.get('signature') or ''
    if signature.startswith('gmail:'):
        return 'mail.google.com'
    return None


def _script_path(ctx: dict) -> str | None:
    plan = ctx.get('plan') or {}
    return (plan.get('context') or {}).get('script_path')


def _task_type(ctx: dict) -> str:
    plan = ctx.get('plan') or {}
    return plan.get('signature') or 'generic:noop'


def _task_goal(ctx: dict) -> str:
    plan = ctx.get('plan') or {}
    return plan.get('goal') or ctx.get('text') or ''


def _derive_outcome(ctx: dict) -> str:
    terminal = ctx.get('terminal_outcome')
    status = ctx.get('status')
    if terminal in {'success', 'failed', 'blocked', 'cancelled', 'needs_user', 'rejected'}:
        return terminal
    if status == 'done':
        return 'success'
    if status == 'needs_user':
        return 'blocked'
    if status == 'awaiting_approval':
        return 'awaiting_approval'
    if status == 'rejected':
        return 'rejected'
    if status == 'partial':
        return 'partial'
    return status or 'unknown'


def _step_history(ctx: dict) -> list[dict]:
    return list(ctx.get('step_history', []))


def _failure_history(ctx: dict) -> list[dict]:
    return list(ctx.get('failure_history', []))


def _repair_history(ctx: dict) -> list[dict]:
    return list(ctx.get('repair_history', []))


def _safety_history(ctx: dict) -> list[dict]:
    return list(ctx.get('safety_history', []))


def _normalized_context(ctx: dict) -> dict:
    plan = ctx.get('plan') or {}
    last_observation = ctx.get('last_observation') or {}
    failure_classes = [item.get('failure_class') for item in _failure_history(ctx) if item.get('failure_class')]
    actions = [item.get('action') for item in _step_history(ctx) if item.get('action')]
    captured = ctx.get('captured_context') or {}
    approval = ctx.get('approval_state') or {}
    draft = ctx.get('draft_state') or {}
    assist = ctx.get('assist') or {}
    return {
        'task_type': _task_type(ctx),
        'script_path': _script_path(ctx),
        'workspace': (plan.get('context') or {}).get('workspace'),
        'domain': _domain_from_context(ctx),
        'failure_classes': sorted(set(failure_classes)),
        'actions': actions,
        'last_failure_class': ctx.get('last_failure_class'),
        'last_action': last_observation.get('last_action'),
        'user_intervention_required': bool(ctx.get('user_intervention_required')),
        'active_app': captured.get('active_app'),
        'input_source': captured.get('input_source'),
        'approval_status': approval.get('status'),
        'draft_style': draft.get('style_hints'),
        'generation_provider': (assist.get('generation') or {}).get('provider'),
        'research_used': assist.get('research_used'),
    }


def _tool_sequence(ctx: dict) -> list[str]:
    sequence: list[str] = []
    for item in _step_history(ctx):
        action = item.get('action')
        if action and (not sequence or sequence[-1] != action):
            sequence.append(action)
    for item in _repair_history(ctx):
        if item.get('strategy') and (not sequence or sequence[-1] != 'CODE_REPAIR'):
            sequence.append('CODE_REPAIR')
    return sequence


def _repairs_that_worked(ctx: dict, outcome: str) -> list[dict]:
    if outcome != 'success':
        return []
    worked: list[dict] = []
    for item in _repair_history(ctx):
        if item.get('ok'):
            worked.append({
                'failure_class': item.get('failure_class'),
                'strategy': item.get('strategy'),
                'change_summary': item.get('change_summary'),
            })
    return worked


def _repairs_that_failed(ctx: dict, outcome: str) -> list[dict]:
    failed: list[dict] = []
    for item in _repair_history(ctx):
        if not item.get('ok'):
            failed.append({
                'failure_class': item.get('failure_class'),
                'strategy': item.get('strategy'),
                'reason': item.get('reason'),
            })
    if outcome != 'success' and not failed and _repair_history(ctx):
        last_repair = _repair_history(ctx)[-1]
        failed.append({
            'failure_class': last_repair.get('failure_class'),
            'strategy': last_repair.get('strategy'),
            'reason': 'final_failure_after_repair',
        })
    return failed


def _candidate_preferences(ctx: dict) -> list[dict]:
    task_type = _task_type(ctx)
    candidates = [
        {
            'scope': task_type,
            'memory_key': key,
            'value': value,
        }
        for key, value in (ctx.get('choices') or {}).items()
    ]
    if task_type == 'assist:writing':
        draft = ctx.get('draft_state') or {}
        styles = draft.get('style_hints') or {}
        if styles.get('length'):
            candidates.append({'scope': task_type, 'memory_key': 'writing.length', 'value': styles['length']})
        if styles.get('tone'):
            candidates.append({'scope': task_type, 'memory_key': 'writing.tone', 'value': styles['tone']})
        approval = ctx.get('approval_state') or {}
        if approval.get('status') in {'approved', 'pasted'}:
            candidates.append({'scope': task_type, 'memory_key': 'assist.approval', 'value': 'required'})
        if (ctx.get('research_context') or {}).get('sources'):
            candidates.append({'scope': task_type, 'memory_key': 'assist.research', 'value': 'useful'})
        if (assist := (ctx.get('assist') or {})).get('generation', {}).get('provider'):
            candidates.append({'scope': task_type, 'memory_key': 'assist.provider', 'value': assist['generation']['provider']})
    return candidates


def _candidate_site_memory(ctx: dict, outcome: str) -> list[dict]:
    domain = _domain_from_context(ctx)
    if not domain:
        return []
    candidates = []
    last_observation = ctx.get('last_observation') or {}
    if last_observation.get('login_required') or ctx.get('user_intervention_required'):
        candidates.append({
            'domain': domain,
            'memory_key': 'login_required',
            'value': 'user_intervention_required',
            'outcome': outcome,
        })
    if outcome == 'success':
        candidates.append({
            'domain': domain,
            'memory_key': 'successful_task_type',
            'value': _task_type(ctx),
            'outcome': outcome,
        })
    if _task_type(ctx) == 'assist:writing':
        approval = ctx.get('approval_state') or {}
        captured = ctx.get('captured_context') or {}
        if captured.get('active_app'):
            candidates.append({
                'domain': domain,
                'memory_key': 'assist.active_app',
                'value': captured.get('active_app'),
                'outcome': outcome,
            })
        if approval.get('status') == 'pasted':
            candidates.append({
                'domain': domain,
                'memory_key': 'assist.pasteback',
                'value': 'success',
                'outcome': outcome,
            })
    return candidates


def _candidate_safety_memory(ctx: dict) -> list[dict]:
    scope = _domain_from_context(ctx) or 'global'
    candidates = []
    for event in _safety_history(ctx):
        if event.get('kind') == 'confirmation':
            candidates.append({
                'scope': scope,
                'action_key': event.get('action'),
                'policy': 'require_confirmation',
            })
        if event.get('kind') == 'blocked':
            candidates.append({
                'scope': scope,
                'action_key': event.get('action'),
                'policy': 'blocked',
            })
    if _task_type(ctx) == 'assist:writing':
        candidates.append({'scope': scope, 'action_key': 'ASSIST_PASTE_BACK', 'policy': 'require_confirmation'})
        if (ctx.get('pasteback_state') or {}).get('status') == 'failed':
            candidates.append({'scope': scope, 'action_key': 'ASSIST_PASTE_BACK', 'policy': 'revalidate_target'})
    return candidates


def _candidate_workflow_patterns(ctx: dict, outcome: str) -> list[dict]:
    task_type = _task_type(ctx)
    candidates = []
    for item in _repair_history(ctx):
        candidates.append({
            'task_type': task_type,
            'pattern_key': f"failure_class:{item.get('failure_class')}",
            'strategy': item.get('strategy'),
            'outcome': 'success' if outcome == 'success' and item.get('ok') else 'failure',
            'notes': item.get('change_summary') or item.get('reason') or '',
        })
    if ctx.get('user_intervention_required'):
        candidates.append({
            'task_type': task_type,
            'pattern_key': f"failure_class:{ctx.get('last_failure_class') or 'manual_intervention'}",
            'strategy': 'escalate_to_user',
            'outcome': 'blocked',
            'notes': 'manual_intervention_required',
        })
    if task_type == 'assist:writing':
        approval = ctx.get('approval_state') or {}
        captured = ctx.get('captured_context') or {}
        research = ctx.get('research_context') or {}
        candidates.append({
            'task_type': task_type,
            'pattern_key': f"task_kind:{(ctx.get('plan') or {}).get('assist', {}).get('task_kind', 'unknown')}",
            'strategy': 'capture_draft_approve_paste',
            'outcome': 'success' if approval.get('status') == 'pasted' else approval.get('status') or outcome,
            'notes': captured.get('input_source') or '',
        })
        if research.get('sources'):
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'research:bounded',
                'strategy': 'page_plus_single_search',
                'outcome': 'success' if approval.get('status') in {'approved', 'pasted'} else outcome,
                'notes': ','.join(research.get('sources', [])[:2]),
            })
        if approval.get('status') == 'rejected':
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'approval:rejected',
                'strategy': 'regenerate_before_paste',
                'outcome': 'failure',
                'notes': approval.get('decision_reason') or '',
            })
    return candidates


def _confidence_signals(ctx: dict, outcome: str) -> dict:
    approval = ctx.get('approval_state') or {}
    return {
        'outcome': outcome,
        'steps_seen': len(_step_history(ctx)),
        'failures_seen': len(_failure_history(ctx)),
        'repairs_attempted': len(_repair_history(ctx)),
        'user_intervention_required': bool(ctx.get('user_intervention_required')),
        'safety_events_seen': len(_safety_history(ctx)),
        'approval_status': approval.get('status'),
        'research_sources_count': len((ctx.get('research_context') or {}).get('sources', [])),
    }


def _useful_observations(ctx: dict) -> list[dict]:
    observations = []
    last_observation = ctx.get('last_observation') or {}
    if last_observation.get('failure_detail'):
        observations.append({'type': 'failure_detail', 'value': last_observation.get('failure_detail')})
    if last_observation.get('traceback_excerpt'):
        observations.append({'type': 'traceback_excerpt', 'value': last_observation.get('traceback_excerpt')})
    if last_observation.get('url'):
        observations.append({'type': 'url', 'value': last_observation.get('url')})
    if (ctx.get('captured_context') or {}).get('input_source'):
        observations.append({'type': 'input_source', 'value': (ctx.get('captured_context') or {}).get('input_source')})
    if (ctx.get('approval_state') or {}).get('status'):
        observations.append({'type': 'approval_status', 'value': (ctx.get('approval_state') or {}).get('status')})
    if ((ctx.get('assist') or {}).get('generation') or {}).get('provider'):
        observations.append({'type': 'generation_provider', 'value': ((ctx.get('assist') or {}).get('generation') or {}).get('provider')})
    return observations


def _future_hints(ctx: dict, outcome: str) -> list[str]:
    hints = []
    repairs_worked = _repairs_that_worked(ctx, outcome)
    repairs_failed = _repairs_that_failed(ctx, outcome)
    if repairs_worked:
        hints.append(f"prefer:{repairs_worked[-1]['strategy']}")
    if repairs_failed:
        hints.append(f"avoid:{repairs_failed[-1]['strategy']}")
    if ctx.get('user_intervention_required'):
        hints.append('escalate_to_user_earlier')
    return hints


def generate_reflection(run_id: str, ctx: dict) -> dict:
    outcome = _derive_outcome(ctx)
    reflection = {
        'run_id': run_id,
        'timestamp': _now_iso(),
        'task_type': _task_type(ctx),
        'task_goal': _task_goal(ctx),
        'normalized_context': _normalized_context(ctx),
        'outcome': outcome,
        'failure_classes_seen': sorted({item.get('failure_class') for item in _failure_history(ctx) if item.get('failure_class')}),
        'repairs_attempted': len(_repair_history(ctx)),
        'repairs_that_worked': _repairs_that_worked(ctx, outcome),
        'repairs_that_failed': _repairs_that_failed(ctx, outcome),
        'user_intervention_required': bool(ctx.get('user_intervention_required')),
        'tool_sequence_used': _tool_sequence(ctx),
        'useful_observations': _useful_observations(ctx),
        'candidate_preferences': _candidate_preferences(ctx),
        'candidate_workflow_patterns': _candidate_workflow_patterns(ctx, outcome),
        'candidate_site_memory': _candidate_site_memory(ctx, outcome),
        'candidate_safety_memory': _candidate_safety_memory(ctx),
        'future_hints': _future_hints(ctx, outcome),
        'confidence_signals': _confidence_signals(ctx, outcome),
    }
    repair_signal = len(reflection['repairs_that_worked']) + len(reflection['repairs_that_failed'])
    reflection['confidence'] = min(0.99, 0.35 + (0.1 * len(reflection['failure_classes_seen'])) + (0.1 * repair_signal))
    return reflection


def persist_reflection(reflection: dict) -> dict:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO reflection_records(
                run_id, timestamp, task_type, task_goal, normalized_context, outcome,
                failure_classes_seen, repairs_attempted, repairs_that_worked, repairs_that_failed,
                user_intervention_required, tool_sequence_used, useful_observations,
                candidate_preferences, candidate_workflow_patterns, candidate_site_memory,
                candidate_safety_memory, future_hints, confidence_signals, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reflection['run_id'],
                reflection['timestamp'],
                reflection['task_type'],
                reflection['task_goal'],
                _json_dumps(reflection['normalized_context']),
                reflection['outcome'],
                _json_dumps(reflection['failure_classes_seen']),
                reflection['repairs_attempted'],
                _json_dumps(reflection['repairs_that_worked']),
                _json_dumps(reflection['repairs_that_failed']),
                int(reflection['user_intervention_required']),
                _json_dumps(reflection['tool_sequence_used']),
                _json_dumps(reflection['useful_observations']),
                _json_dumps(reflection['candidate_preferences']),
                _json_dumps(reflection['candidate_workflow_patterns']),
                _json_dumps(reflection['candidate_site_memory']),
                _json_dumps(reflection['candidate_safety_memory']),
                _json_dumps(reflection['future_hints']),
                _json_dumps(reflection['confidence_signals']),
                reflection['confidence'],
            ),
        )
    return reflection


def _deserialize_reflection(row: dict) -> dict:
    row['normalized_context'] = _json_loads(row.get('normalized_context'), {})
    row['failure_classes_seen'] = _json_loads(row.get('failure_classes_seen'), [])
    row['repairs_that_worked'] = _json_loads(row.get('repairs_that_worked'), [])
    row['repairs_that_failed'] = _json_loads(row.get('repairs_that_failed'), [])
    row['tool_sequence_used'] = _json_loads(row.get('tool_sequence_used'), [])
    row['useful_observations'] = _json_loads(row.get('useful_observations'), [])
    row['candidate_preferences'] = _json_loads(row.get('candidate_preferences'), [])
    row['candidate_workflow_patterns'] = _json_loads(row.get('candidate_workflow_patterns'), [])
    row['candidate_site_memory'] = _json_loads(row.get('candidate_site_memory'), [])
    row['candidate_safety_memory'] = _json_loads(row.get('candidate_safety_memory'), [])
    row['future_hints'] = _json_loads(row.get('future_hints'), [])
    row['confidence_signals'] = _json_loads(row.get('confidence_signals'), {})
    return row


def list_reflection_records(limit: int = 100) -> list[dict]:
    rows = get_conn().execute(
        'SELECT * FROM reflection_records ORDER BY timestamp DESC LIMIT ?',
        (limit,),
    ).fetchall()
    return [_deserialize_reflection(dict(row)) for row in rows]


def _workflow_confidence(success_count: int, failure_count: int) -> float:
    evidence = success_count + failure_count
    if evidence == 0:
        return 0.0
    return round(min(0.99, 0.4 + (0.12 * evidence) + (0.08 * max(success_count - failure_count, 0))), 2)


def _evidence_confidence(evidence_count: int) -> float:
    return round(min(0.99, 0.35 + (0.15 * evidence_count)), 2)


def consolidate_learning() -> dict:
    reflections = list_reflection_records(limit=REFLECTION_LIMIT)
    workflow_rollups: dict[tuple[str, str, str], dict] = {}
    preference_rollups: dict[tuple[str, str, str], dict] = {}
    site_rollups: dict[tuple[str, str, str], dict] = {}
    safety_rollups: dict[tuple[str, str, str], dict] = {}

    for reflection in reflections:
        timestamp = reflection.get('timestamp') or _now_iso()
        for candidate in reflection.get('candidate_workflow_patterns', []):
            key = (candidate.get('task_type') or reflection.get('task_type'), candidate.get('pattern_key'), candidate.get('strategy'))
            row = workflow_rollups.setdefault(key, {
                'task_type': key[0],
                'pattern_key': key[1],
                'strategy': key[2],
                'success_count': 0,
                'failure_count': 0,
                'last_seen': timestamp,
                'notes': [],
            })
            if candidate.get('outcome') == 'success':
                row['success_count'] += 1
            else:
                row['failure_count'] += 1
            row['last_seen'] = max(row['last_seen'], timestamp)
            if candidate.get('notes'):
                row['notes'].append(candidate['notes'])

        for candidate in reflection.get('candidate_preferences', []):
            key = (candidate.get('scope'), candidate.get('memory_key'), str(candidate.get('value')))
            row = preference_rollups.setdefault(key, {
                'scope': key[0],
                'memory_key': key[1],
                'value': key[2],
                'evidence_count': 0,
                'last_seen': timestamp,
            })
            row['evidence_count'] += 1
            row['last_seen'] = max(row['last_seen'], timestamp)

        for candidate in reflection.get('candidate_site_memory', []):
            key = (candidate.get('domain'), candidate.get('memory_key'), candidate.get('value'))
            row = site_rollups.setdefault(key, {
                'domain': key[0],
                'memory_key': key[1],
                'value': key[2],
                'success_count': 0,
                'failure_count': 0,
                'last_seen': timestamp,
            })
            if candidate.get('outcome') == 'success':
                row['success_count'] += 1
            else:
                row['failure_count'] += 1
            row['last_seen'] = max(row['last_seen'], timestamp)

        for candidate in reflection.get('candidate_safety_memory', []):
            key = (candidate.get('scope'), candidate.get('action_key'), candidate.get('policy'))
            row = safety_rollups.setdefault(key, {
                'scope': key[0],
                'action_key': key[1],
                'policy': key[2],
                'evidence_count': 0,
                'last_seen': timestamp,
            })
            row['evidence_count'] += 1
            row['last_seen'] = max(row['last_seen'], timestamp)

    with get_conn() as conn:
        conn.execute('DELETE FROM workflow_memory')
        conn.execute('DELETE FROM preference_memory')
        conn.execute('DELETE FROM site_memory')
        conn.execute('DELETE FROM safety_memory')

        for row in workflow_rollups.values():
            total = row['success_count'] + row['failure_count']
            if total <= 0:
                continue
            conn.execute(
                """
                INSERT INTO workflow_memory(
                    task_type, pattern_key, strategy, confidence, success_count, failure_count, last_seen, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row['task_type'],
                    row['pattern_key'],
                    row['strategy'],
                    _workflow_confidence(row['success_count'], row['failure_count']),
                    row['success_count'],
                    row['failure_count'],
                    row['last_seen'],
                    '; '.join(sorted(set(row['notes']))[:3]),
                ),
            )

        for row in preference_rollups.values():
            if row['evidence_count'] < 2:
                continue
            conn.execute(
                """
                INSERT INTO preference_memory(
                    scope, memory_key, value, confidence, evidence_count, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row['scope'],
                    row['memory_key'],
                    row['value'],
                    _evidence_confidence(row['evidence_count']),
                    row['evidence_count'],
                    row['last_seen'],
                ),
            )

        for row in site_rollups.values():
            total = row['success_count'] + row['failure_count']
            if total < 2 and row['failure_count'] == 0:
                continue
            conn.execute(
                """
                INSERT INTO site_memory(
                    domain, memory_key, value, confidence, success_count, failure_count, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row['domain'],
                    row['memory_key'],
                    row['value'],
                    _workflow_confidence(row['success_count'], row['failure_count']),
                    row['success_count'],
                    row['failure_count'],
                    row['last_seen'],
                ),
            )

        for row in safety_rollups.values():
            if row['evidence_count'] < 2:
                continue
            conn.execute(
                """
                INSERT INTO safety_memory(
                    scope, action_key, policy, confidence, evidence_count, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row['scope'],
                    row['action_key'],
                    row['policy'],
                    _evidence_confidence(row['evidence_count']),
                    row['evidence_count'],
                    row['last_seen'],
                ),
            )

    return {
        'reflections_considered': len(reflections),
        'workflow_entries': len(workflow_rollups),
        'preference_entries': len([row for row in preference_rollups.values() if row['evidence_count'] >= 2]),
        'site_entries': len([row for row in site_rollups.values() if (row['success_count'] + row['failure_count'] >= 2 or row['failure_count'] > 0)]),
        'safety_entries': len([row for row in safety_rollups.values() if row['evidence_count'] >= 2]),
    }


def list_workflow_memory() -> list[dict]:
    rows = get_conn().execute(
        'SELECT * FROM workflow_memory ORDER BY confidence DESC, success_count DESC, id DESC',
    ).fetchall()
    return [dict(row) for row in rows]


def list_preference_memory() -> list[dict]:
    rows = get_conn().execute(
        'SELECT * FROM preference_memory ORDER BY confidence DESC, evidence_count DESC, id DESC',
    ).fetchall()
    return [dict(row) for row in rows]


def list_site_memory() -> list[dict]:
    rows = get_conn().execute(
        'SELECT * FROM site_memory ORDER BY confidence DESC, failure_count DESC, id DESC',
    ).fetchall()
    return [dict(row) for row in rows]


def list_safety_memory() -> list[dict]:
    rows = get_conn().execute(
        'SELECT * FROM safety_memory ORDER BY confidence DESC, evidence_count DESC, id DESC',
    ).fetchall()
    return [dict(row) for row in rows]


def query_relevant_memory(
    *,
    task_type: str | None = None,
    domain: str | None = None,
    failure_class: str | None = None,
    action_key: str | None = None,
    limit: int = RELEVANT_MEMORY_LIMIT,
) -> dict:
    workflow = []
    for row in list_workflow_memory():
        score = 0
        if task_type and row['task_type'] == task_type:
            score += 3
        if failure_class and failure_class in (row.get('pattern_key') or ''):
            score += 4
        if score:
            workflow.append({**row, 'score': score})

    preferences = []
    for row in list_preference_memory():
        score = 0
        if task_type and row['scope'] == task_type:
            score += 3
        if row['scope'] == 'global':
            score += 1
        if score:
            preferences.append({**row, 'score': score})

    sites = []
    for row in list_site_memory():
        score = 0
        if domain and row['domain'] == domain:
            score += 4
        if score:
            sites.append({**row, 'score': score})

    safety = []
    for row in list_safety_memory():
        score = 0
        if action_key and row['action_key'] == action_key:
            score += 4
        if domain and row['scope'] == domain:
            score += 2
        if row['scope'] == 'global':
            score += 1
        if score:
            safety.append({**row, 'score': score})

    return {
        'workflow': sorted(workflow, key=lambda item: (item['score'], item['confidence'], item['success_count']), reverse=True)[:limit],
        'preferences': sorted(preferences, key=lambda item: (item['score'], item['confidence'], item['evidence_count']), reverse=True)[:limit],
        'site': sorted(sites, key=lambda item: (item['score'], item['confidence'], item['failure_count']), reverse=True)[:limit],
        'safety': sorted(safety, key=lambda item: (item['score'], item['confidence'], item['evidence_count']), reverse=True)[:limit],
    }


def workflow_guidance(*, task_type: str, failure_class: str | None) -> dict:
    relevant = query_relevant_memory(task_type=task_type, failure_class=failure_class)
    successful = [item for item in relevant['workflow'] if item['success_count'] > item['failure_count']]
    failed = [item for item in relevant['workflow'] if item['failure_count'] >= max(1, item['success_count'])]
    blocked = [item for item in relevant['workflow'] if item['strategy'] == 'escalate_to_user' and item['failure_count'] >= 2]
    return {
        'preferred_strategy': successful[0]['strategy'] if successful else None,
        'failed_strategies': [item['strategy'] for item in failed],
        'avoid_strategy': failed[0]['strategy'] if failed and failed[0]['failure_count'] >= 2 and failed[0]['success_count'] == 0 else None,
        'escalate_early': bool(blocked),
        'relevant_memory': relevant,
    }


def record_run_learning(run_id: str, ctx: dict) -> dict:
    reflection = persist_reflection(generate_reflection(run_id, ctx))
    consolidation = consolidate_learning()
    return {'reflection': reflection, 'consolidation': consolidation}
