from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from storage.db import get_conn


REFLECTION_LIMIT = 200
RELEVANT_MEMORY_LIMIT = 5
STYLE_DIMENSIONS = {
    'length_preference': 'writing.length',
    'tone_preference': 'writing.tone',
    'warmth_preference': 'writing.warmth',
    'structure_preference': 'writing.structure',
    'research_tendency': 'assist.research',
}


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
    fingerprint = ((ctx.get('captured_context') or {}).get('target_fingerprint') or {})
    if fingerprint.get('browser_domain'):
        return fingerprint.get('browser_domain')
    if fingerprint.get('browser_url'):
        return _domain_from_url(fingerprint.get('browser_url'))
    for step in plan.get('steps', []):
        url = (step.get('args') or {}).get('url')
        domain = _domain_from_url(url)
        if domain:
            return domain
    signature = plan.get('signature') or ''
    if signature.startswith('gmail:'):
        return 'mail.google.com'
    return None


def _active_app_from_context(ctx: dict) -> str | None:
    captured = ctx.get('captured_context') or {}
    app_name = captured.get('active_app') or ((captured.get('target_fingerprint') or {}).get('app_name'))
    if app_name:
        return str(app_name)
    normalized = ((captured.get('target_fingerprint') or {}).get('normalized') or {})
    return normalized.get('app_name')


def _normalize_app_name(app_name: str | None) -> str | None:
    if not app_name:
        return None
    return ''.join(ch.lower() for ch in str(app_name) if ch.isalnum())


def _scope_variants(*, task_type: str, active_app: str | None, domain: str | None) -> list[tuple[str, int]]:
    app_key = _normalize_app_name(active_app)
    variants: list[tuple[str, int]] = []
    if app_key and domain:
        variants.append((f'{task_type}|app:{app_key}|domain:{domain}', 6))
    if app_key:
        variants.append((f'{task_type}|app:{app_key}', 5))
    if domain:
        variants.append((f'{task_type}|domain:{domain}', 5))
    variants.append((task_type, 3))
    variants.append(('global', 1))
    return variants


def _confidence_from_counts(*, support: int, contradiction: int) -> float:
    evidence = support + contradiction
    if evidence <= 0:
        return 0.0
    score = 0.32 + (0.12 * evidence) + (0.08 * max(support - contradiction, 0)) - (0.08 * contradiction)
    return round(max(0.05, min(0.99, score)), 2)


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


def _guardian_history(ctx: dict) -> list[dict]:
    return list(ctx.get('guardian_events', []))


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
        'guardian_risks': sorted({item.get('risk') for item in _guardian_history(ctx) if item.get('risk')}),
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
    active_app = _active_app_from_context(ctx)
    domain = _domain_from_context(ctx)
    scopes = [task_type]
    app_key = _normalize_app_name(active_app)
    if app_key and domain:
        scopes.append(f'{task_type}|app:{app_key}|domain:{domain}')
    if app_key:
        scopes.append(f'{task_type}|app:{app_key}')
    if domain:
        scopes.append(f'{task_type}|domain:{domain}')
    candidates = [
        {
            'scope': scope,
            'memory_key': key,
            'value': value,
        }
        for scope in scopes
        for key, value in (ctx.get('choices') or {}).items()
    ]
    if task_type == 'assist:writing':
        draft = ctx.get('draft_state') or {}
        styles = draft.get('style_hints') or {}
        edit_signals = ((ctx.get('assist') or {}).get('edit_signals') or {})
        resolved_length = edit_signals.get('length_preference') or styles.get('length')
        resolved_tone = edit_signals.get('tone_preference') or styles.get('tone')
        resolved_warmth = edit_signals.get('warmth_preference')
        resolved_structure = edit_signals.get('structure_preference')
        for scope in scopes:
            if resolved_length:
                candidates.append({'scope': scope, 'memory_key': 'writing.length', 'value': resolved_length})
            if resolved_tone:
                candidates.append({'scope': scope, 'memory_key': 'writing.tone', 'value': resolved_tone})
            if resolved_warmth:
                candidates.append({'scope': scope, 'memory_key': 'writing.warmth', 'value': resolved_warmth})
            if resolved_structure:
                candidates.append({'scope': scope, 'memory_key': 'writing.structure', 'value': resolved_structure})
        approval = ctx.get('approval_state') or {}
        if approval.get('status') in {'approved', 'pasted'}:
            for scope in scopes:
                candidates.append({'scope': scope, 'memory_key': 'assist.approval', 'value': 'required'})
        if (ctx.get('research_context') or {}).get('sources'):
            research_value = edit_signals.get('research_tendency') or 'prefer'
            for scope in scopes:
                candidates.append({'scope': scope, 'memory_key': 'assist.research', 'value': research_value})
        if (assist := (ctx.get('assist') or {})).get('generation', {}).get('provider'):
            for scope in scopes:
                candidates.append({'scope': scope, 'memory_key': 'assist.provider', 'value': assist['generation']['provider']})
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
        pasteback = ctx.get('pasteback_state') or {}
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
        if captured.get('capture_path_used'):
            candidates.append({
                'domain': domain,
                'memory_key': 'assist.capture_path',
                'value': captured.get('capture_path_used'),
                'outcome': outcome,
            })
        if pasteback.get('target_validation_result'):
            candidates.append({
                'domain': domain,
                'memory_key': 'assist.pasteback.validation',
                'value': pasteback.get('target_validation_result'),
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
    guardian_events = _guardian_history(ctx)
    for event in guardian_events:
        risk = event.get('risk')
        if risk in {'medium', 'high'}:
            candidates.append({
                'scope': scope,
                'action_key': event.get('action') or event.get('type'),
                'policy': 'require_confirmation' if risk == 'medium' else 'revalidate_target',
            })
    if sum(1 for event in guardian_events if event.get('type') == 'clipboard_read') >= 2:
        candidates.append({'scope': scope, 'action_key': 'OS_COPY_SELECTION', 'policy': 'require_confirmation'})
    if any(event.get('type') == 'network_action' for event in guardian_events):
        candidates.append({'scope': scope, 'action_key': 'WEB_READ', 'policy': 'require_confirmation'})
    if _task_type(ctx) == 'assist:writing':
        candidates.append({'scope': scope, 'action_key': 'ASSIST_PASTE_BACK', 'policy': 'require_confirmation'})
        if (ctx.get('pasteback_state') or {}).get('status') == 'failed':
            candidates.append({'scope': scope, 'action_key': 'ASSIST_PASTE_BACK', 'policy': 'revalidate_target'})
        if (ctx.get('pasteback_state') or {}).get('target_validation_result') == 'drifted':
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
        pasteback = ctx.get('pasteback_state') or {}
        edit_signals = ((ctx.get('assist') or {}).get('edit_signals') or {})
        proactive = ctx.get('proactive') or {}
        candidates.append({
            'task_type': task_type,
            'pattern_key': f"task_kind:{(ctx.get('plan') or {}).get('assist', {}).get('task_kind', 'unknown')}",
            'strategy': 'capture_draft_approve_paste',
            'outcome': 'success' if approval.get('status') == 'pasted' else approval.get('status') or outcome,
            'notes': captured.get('input_source') or '',
        })
        if proactive.get('suggestion_selected'):
            selected_action = proactive.get('suggestion_selected')
            selected_outcome = 'success' if approval.get('status') == 'pasted' else ('failure' if approval.get('status') == 'rejected' else outcome)
            candidates.append({
                'task_type': task_type,
                'pattern_key': f'proactive:{selected_action}:selected',
                'strategy': 'overlay_proactive_suggestion',
                'outcome': selected_outcome,
                'notes': ','.join(signal.get('name', '') for signal in proactive.get('signals_used', [])[:3]),
            })
            if approval.get('status') == 'rejected':
                candidates.append({
                    'task_type': task_type,
                    'pattern_key': f'proactive:{selected_action}:rejected',
                    'strategy': 'overlay_proactive_suggestion',
                    'outcome': 'failure',
                    'notes': approval.get('decision_reason') or '',
                })
        if captured.get('capture_path_used'):
            candidates.append({
                'task_type': task_type,
                'pattern_key': f"capture_path:{captured.get('capture_path_used')}",
                'strategy': 'capture_context',
                'outcome': outcome,
                'notes': (captured.get('capture_method') or {}).get('capture_failure_reason') or '',
            })
        if research.get('sources'):
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'research:bounded',
                'strategy': 'page_plus_single_search',
                'outcome': 'success' if approval.get('status') in {'approved', 'pasted'} else outcome,
                'notes': ','.join(research.get('sources', [])[:2]),
            })
        guardian_events = _guardian_history(ctx)
        for event in guardian_events:
            event_type = event.get('type')
            if not event_type:
                continue
            event_risk = event.get('risk') or 'unknown'
            candidates.append({
                'task_type': task_type,
                'pattern_key': f'guardian:{event_type}:{event_risk}',
                'strategy': 'guardian_observer',
                'outcome': 'success' if event_risk == 'low' else ('blocked' if event_risk == 'high' else outcome),
                'notes': str((event.get('context') or {}).get('target') or event.get('summary') or ''),
            })
        if sum(1 for event in guardian_events if event.get('type') == 'clipboard_read') >= 2:
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'guardian:repeated_clipboard_access',
                'strategy': 'guardian_observer',
                'outcome': outcome,
                'notes': 'repeated_clipboard_access',
            })
        if any(event.get('type') == 'network_action' for event in guardian_events):
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'guardian:external_browser_access',
                'strategy': 'guardian_observer',
                'outcome': outcome,
                'notes': 'external_browser_access',
            })
        if any(event.get('type') == 'clipboard_write' and (event.get('context') or {}).get('size', 0) >= 600 for event in guardian_events):
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'guardian:large_pasteback',
                'strategy': 'guardian_observer',
                'outcome': outcome,
                'notes': 'large_pasteback',
            })
        if approval.get('status') == 'rejected':
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'approval:rejected',
                'strategy': 'regenerate_before_paste',
                'outcome': 'failure',
                'notes': approval.get('decision_reason') or '',
            })
        if approval.get('status') in {'approved', 'pasted'}:
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'approval:edited' if edit_signals.get('edited') else 'approval:unchanged',
                'strategy': 'explicit_review_before_paste',
                'outcome': 'success',
                'notes': edit_signals.get('summary') or '',
            })
        if approval.get('feedback'):
            candidates.append({
                'task_type': task_type,
                'pattern_key': 'approval:retry',
                'strategy': 'regenerate_before_paste',
                'outcome': 'success' if approval.get('status') in {'approved', 'pasted'} else outcome,
                'notes': approval.get('feedback') or '',
            })
        if pasteback.get('target_validation_result'):
            candidates.append({
                'task_type': task_type,
                'pattern_key': f"paste_validation:{pasteback.get('target_validation_result')}",
                'strategy': 'reactivate_revalidate_paste',
                'outcome': 'success' if pasteback.get('status') == 'pasted' else outcome,
                'notes': pasteback.get('context_drift_reason') or pasteback.get('paste_blocked_reason') or '',
            })
        if pasteback.get('context_drift_reason'):
            candidates.append({
                'task_type': task_type,
                'pattern_key': f"failure_class:{pasteback.get('context_drift_reason')}",
                'strategy': 'revalidate_before_paste',
                'outcome': 'failure',
                'notes': pasteback.get('paste_blocked_reason') or '',
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
    if (ctx.get('captured_context') or {}).get('capture_path_used'):
        observations.append({'type': 'capture_path_used', 'value': (ctx.get('captured_context') or {}).get('capture_path_used')})
    if (ctx.get('approval_state') or {}).get('status'):
        observations.append({'type': 'approval_status', 'value': (ctx.get('approval_state') or {}).get('status')})
    if ((ctx.get('assist') or {}).get('generation') or {}).get('provider'):
        observations.append({'type': 'generation_provider', 'value': ((ctx.get('assist') or {}).get('generation') or {}).get('provider')})
    if (ctx.get('pasteback_state') or {}).get('target_validation_result'):
        observations.append({'type': 'target_validation_result', 'value': (ctx.get('pasteback_state') or {}).get('target_validation_result')})
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
    pasteback = ctx.get('pasteback_state') or {}
    if pasteback.get('target_validation_result') == 'drifted':
        hints.append('revalidate_before_paste')
    if (ctx.get('captured_context') or {}).get('capture_path_used') == 'clipboard_fallback':
        hints.append('prefer_clipboard_fallback_when_selection_fails')
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


def resolve_assist_profile(
    *,
    task_kind: str,
    active_app: str | None = None,
    domain: str | None = None,
    task_type: str = 'assist:writing',
) -> dict:
    from .prefs import get_pref_value

    scopes = _scope_variants(task_type=task_type, active_app=active_app, domain=domain)
    preferences = list_preference_memory()
    workflow = list_workflow_memory()
    safety = list_safety_memory()

    profile_dimensions: dict[str, dict] = {}
    for dimension, memory_key in STYLE_DIMENSIONS.items():
        candidates: list[dict] = []
        for scope_name, scope_weight in scopes:
            for row in preferences:
                if row['scope'] != scope_name or row['memory_key'] != memory_key:
                    continue
                candidates.append({
                    'value': row['value'],
                    'scope': scope_name,
                    'scope_weight': scope_weight,
                    'confidence': row['confidence'],
                    'evidence_count': row['evidence_count'],
                })
        if not candidates:
            pref_key = f'assist.{task_kind}.{memory_key.split(".")[-1]}' if memory_key.startswith('writing.') else memory_key
            fallback = get_pref_value(pref_key) or get_pref_value(memory_key) or (
                'auto' if memory_key == 'assist.research' else
                'summary_first' if memory_key == 'writing.structure' else
                'neutral' if memory_key == 'writing.warmth' else
                'polished' if memory_key == 'writing.tone' else
                'concise'
            )
            profile_dimensions[dimension] = {
                'value': fallback,
                'confidence': 0.25,
                'scope': 'fallback',
                'evidence_count': 0,
                'conflicts': [],
            }
            continue
        value_rollup: dict[str, dict] = {}
        for candidate in candidates:
            bucket = value_rollup.setdefault(candidate['value'], {
                'value': candidate['value'],
                'support': 0,
                'scope_weight': 0,
                'best_confidence': 0.0,
                'evidence_count': 0,
                'scope': candidate['scope'],
            })
            bucket['support'] += max(1, candidate['evidence_count'])
            bucket['scope_weight'] = max(bucket['scope_weight'], candidate['scope_weight'])
            bucket['best_confidence'] = max(bucket['best_confidence'], candidate['confidence'])
            bucket['evidence_count'] += candidate['evidence_count']
            if candidate['scope_weight'] >= bucket['scope_weight']:
                bucket['scope'] = candidate['scope']
        ranked = sorted(
            value_rollup.values(),
            key=lambda item: (item['scope_weight'], item['support'], item['best_confidence']),
            reverse=True,
        )
        winner = ranked[0]
        contradiction = sum(item['support'] for item in ranked[1:])
        profile_dimensions[dimension] = {
            'value': winner['value'],
            'confidence': max(round(winner['best_confidence'], 2), _confidence_from_counts(support=winner['support'], contradiction=contradiction)),
            'scope': winner['scope'],
            'evidence_count': winner['evidence_count'],
            'conflicts': [item['value'] for item in ranked[1:3]],
        }

    task_pattern = f'task_kind:{task_kind}'
    relevant_task_patterns = [row for row in workflow if row['task_type'] == task_type and row['pattern_key'] == task_pattern]
    unchanged = sum(row['success_count'] for row in workflow if row['task_type'] == task_type and row['pattern_key'] == 'approval:unchanged')
    edited = sum(row['success_count'] for row in workflow if row['task_type'] == task_type and row['pattern_key'] == 'approval:edited')
    retries = sum(row['success_count'] + row['failure_count'] for row in workflow if row['task_type'] == task_type and row['pattern_key'] == 'approval:retry')
    rejections = sum(row['failure_count'] + row['success_count'] for row in workflow if row['task_type'] == task_type and row['pattern_key'] == 'approval:rejected')
    domain_safety = [row for row in safety if row['action_key'] == 'ASSIST_PASTE_BACK' and row['scope'] in {domain, 'global'}]
    edit_total = unchanged + edited
    approval_confidence = _confidence_from_counts(support=unchanged, contradiction=edited + rejections)
    caution = 'normal'
    if rejections >= 2 or edited > unchanged:
        caution = 'strict'
    elif edited or retries or any(row['policy'] == 'revalidate_target' for row in domain_safety):
        caution = 'elevated'

    applied = {
        'length': profile_dimensions['length_preference']['value'],
        'tone': profile_dimensions['tone_preference']['value'],
        'warmth': profile_dimensions['warmth_preference']['value'],
        'structure': profile_dimensions['structure_preference']['value'],
        'research': profile_dimensions['research_tendency']['value'],
    }

    hints: list[str] = []
    if active_app:
        hints.append(f'app:{active_app}')
    if domain:
        hints.append(f'domain:{domain}')
    if relevant_task_patterns:
        hints.append(f'task_kind:{task_kind}')

    return {
        'task_kind': task_kind,
        'task_type': task_type,
        'active_app': active_app,
        'domain': domain,
        'style_profile': profile_dimensions,
        'approval_profile': {
            'approval_confidence': approval_confidence,
            'edit_frequency': round(edited / edit_total, 2) if edit_total else 0.0,
            'edit_count': edited,
            'unchanged_count': unchanged,
            'retry_count': retries,
            'rejection_count': rejections,
            'recommended_caution': caution,
            'auto_approve_ready': bool(unchanged >= 3 and edited == 0 and rejections == 0),
            'safety_policies': [row['policy'] for row in domain_safety[:3]],
        },
        'applied_signals': applied,
        'hints': hints,
    }


def suggest_assist_actions(*, captured_context: dict | None = None, task_type: str = 'assist:writing') -> list[dict]:
    context = captured_context or {}
    active_app = context.get('active_app')
    domain = _domain_from_url(context.get('browser_url')) or ((context.get('target_fingerprint') or {}).get('browser_domain'))
    app_key = (_normalize_app_name(active_app) or '')
    has_input = bool(context.get('input_text'))
    profile = resolve_assist_profile(task_kind='summarize', active_app=active_app, domain=domain, task_type=task_type)
    research_pref = ((profile.get('style_profile') or {}).get('research_tendency') or {}).get('value', 'auto')

    candidates = [
        {'label': 'Reply to this', 'command': 'Draft a reply to this', 'reason': 'Best for active message or email context.', 'base': 0.45},
        {'label': 'Summarize this', 'command': 'Summarize this', 'reason': 'Useful when text is already selected.', 'base': 0.4},
        {'label': 'Rewrite this better', 'command': 'Rewrite this better', 'reason': 'Good for polishing text in place.', 'base': 0.38},
        {'label': 'Explain this', 'command': 'Explain this', 'reason': 'Useful for understanding selected content.', 'base': 0.34},
        {'label': 'Answer with research', 'command': 'Research this and answer', 'reason': 'Good when you need a grounded answer.', 'base': 0.33},
    ]
    workflow = list_workflow_memory()
    task_scores = {
        row['pattern_key'].split(':', 1)[1]: row['success_count'] - row['failure_count']
        for row in workflow
        if row['task_type'] == task_type and (row.get('pattern_key') or '').startswith('task_kind:')
    }

    suggestions: list[dict] = []
    for candidate in candidates:
        score = candidate['base']
        command = candidate['command']
        label = candidate['label']
        reasons = [candidate['reason']]
        if has_input:
            score += 0.18
            reasons.append('Selected or copied text is available.')
        if 'reply' in command.lower() and ('mail' in app_key or (domain and 'mail' in domain)):
            score += 0.26
            reasons.append('Current app/domain looks like email or messaging.')
        if 'rewrite' in command.lower() and active_app:
            score += 0.12
        if 'research' in command.lower() and research_pref == 'prefer':
            score += 0.2
            reasons.append('Past behavior suggests source-backed answers are preferred here.')
        if label.lower().startswith('summarize') and task_scores.get('summarize', 0) > 0:
            score += 0.08
        if label.lower().startswith('reply') and task_scores.get('reply', 0) > 0:
            score += 0.08
        if label.lower().startswith('rewrite') and task_scores.get('rewrite', 0) > 0:
            score += 0.08
        suggestions.append({
            'label': label,
            'command': command,
            'confidence': round(min(0.98, score), 2),
            'reason': ' '.join(reasons),
        })
    suggestions.sort(key=lambda item: item['confidence'], reverse=True)
    return suggestions[:4]


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
