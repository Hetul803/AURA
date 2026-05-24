from __future__ import annotations

import json
import re
import time
import uuid

from .assist import apply_feedback_preferences, draft_from_state
from .context_engine import capture_current_context
from .crypto_identity import sign_identity_payload
from .executor import execute_steps
from .guardian import record_human_guardian_event
from .identity_boundary import get_active_identity, memory_scope_decision
from .learning import record_run_learning
from .macros import match_macro, record_macro, render_macro_steps, touch_macro
from .memory import remember_execution, write_memory
from .memory_engine import remember_item, search_memory_items
from .planner import plan_from_text
from .prefs import set_pref
from .state import decide_approval, get_run_context, record_audit_event, record_run_event, set_run_context, update_run_context
from .steps import Step
from .workflow_engine import create_workflow


def _send_event(event_cb, event: dict):
    record_run_event(event)
    event_cb(event)


def _materialize_steps(plan: dict, use_macro: bool = False):
    macro = match_macro(plan['signature'])
    if macro and use_macro:
        touch_macro(macro['id'])
        return [Step(**s) for s in render_macro_steps(macro, plan.get('slots'))], macro
    return plan['steps'], macro


def _memory_detail(text: str, extra: dict | None = None) -> str:
    return json.dumps({'detail': text, 'extra': extra or {}}, sort_keys=True)


def _status_from_result(result: list[dict]) -> str:
    if not result:
        return 'done'
    last = result[-1]
    if last['status'] == 'needs_user':
        return 'needs_user'
    if last['status'] == 'awaiting_approval':
        return 'awaiting_approval'
    if last['status'] == 'rejected':
        return 'rejected'
    if last['status'] == 'blocked':
        return 'blocked'
    if last['status'] == 'cancelled':
        return 'cancelled'
    return 'done' if all(r['status'] == 'success' for r in result) else 'partial'


def _capture_planning_context() -> dict:
    try:
        return capture_current_context(source='command')
    except Exception as exc:
        return {'ok': False, 'source': 'command', 'error': str(exc), 'context_refs': []}


def _path_from_memory(value: str) -> str | None:
    match = re.search(r'(~?/[\w .@%+=:,/\\-]+)', value or '')
    if match:
        return match.group(1).strip().rstrip('.')
    return None


def _identity_context() -> dict:
    identity = get_active_identity()
    return {
        'active_identity': identity,
        'identity_id': identity.get('identity_id'),
        'identity_name': identity.get('name'),
        'identity_scope': identity.get('memory_scope') or 'personal',
    }


def _signed_identity_payload(identity: dict, payload: dict) -> dict:
    enriched = dict(payload)
    try:
        enriched['identity_signature'] = sign_identity_payload(identity.get('identity_id') or 'personal', enriched)
    except Exception as exc:
        enriched['identity_signature_error'] = str(exc)
    return enriched


def _relevant_memory_for_command(text: str, identity: dict, task_type: str | None = None) -> dict:
    scope = identity.get('memory_scope') or 'personal'
    items = search_memory_items(text, scope=scope, task_type=task_type, permission='private', limit=5)
    workspace_hint = None
    for item in items:
        key = str(item.get('memory_key') or '').lower()
        value = str(item.get('value') or '')
        if any(token in key for token in ['workspace', 'folder', 'clone.path', 'project.folder']):
            workspace_hint = _path_from_memory(value)
            if workspace_hint:
                break
    return {
        'items': [
            {
                'memory_id': item.get('memory_id'),
                'kind': item.get('kind'),
                'scope': item.get('scope'),
                'memory_key': item.get('memory_key'),
                'score': item.get('score'),
                'reason': f"Matched this command under {scope} identity scope.",
            }
            for item in items
        ],
        'workspace_hint': workspace_hint,
    }


def _memory_request_payload(text: str) -> tuple[str, str] | None:
    low = text.lower().strip()
    if low.startswith('remember this '):
        value = text[len('remember this '):].strip()
    elif low.startswith('remember '):
        value = text[len('remember '):].strip()
    else:
        return None
    if not value:
        return None
    key = 'user.note'
    if '=' in value:
        key = value.split('=', 1)[0].strip().replace(' ', '_') or key
    return key, value


def _run_memory_request(run_id: str, text: str, planning_context: dict, event_cb) -> dict | None:
    payload = _memory_request_payload(text)
    if not payload:
        return None
    key, value = payload
    identity = (planning_context.get('identity') or {}).get('active_identity') or get_active_identity()
    scope_decision = memory_scope_decision(requested_scope=identity.get('memory_scope') or 'personal', action='remember', active_identity=identity)
    result = remember_item(
        kind='preference' if any(token in value.lower() for token in ['prefer', 'preference', 'always', 'usually']) else 'note',
        key=key,
        value=value,
        scope=scope_decision['scope'],
        permission='private',
        source='user',
        confidence=0.75,
        provenance={'run_id': run_id, 'source': 'command', 'active_identity': identity.get('identity_id')},
        metadata={'active_identity': identity.get('identity_id'), 'identity_scope': scope_decision['scope']},
    )
    status = 'blocked' if result.get('rejected') else 'done'
    set_run_context(run_id, {
        'text': text,
        'choices': {},
        'use_macro': False,
        'status': status,
        'planning_context': planning_context,
        'plan': {'signature': 'memory:write', 'goal': 'Save useful memory safely', 'steps': []},
        'steps': [],
        'current_step_index': 0,
        'terminal_outcome': 'blocked' if result.get('rejected') else 'success',
        'approval_state': {'required': False, 'status': 'not_requested'},
        'memory_result': result,
        'identity': planning_context.get('identity'),
    })
    audit_payload = _signed_identity_payload(identity, {
        'identity_id': identity.get('identity_id'),
        'identity_name': identity.get('name'),
        'memory_scope': scope_decision['scope'],
        'memory_key': key,
        'stored': bool(result.get('stored')),
        'rejected': bool(result.get('rejected')),
        'reasons': result.get('reasons') or [],
    })
    record_audit_event({
        'run_id': run_id,
        'event_type': 'memory_write_blocked' if result.get('rejected') else 'memory_write_saved',
        'action_type': 'MEMORY_WRITE',
        'risk_level': 'blocked' if result.get('rejected') else 'low',
        'message': f"AURA acted under {identity.get('name') or identity.get('identity_id')} to evaluate memory storage.",
        'payload': audit_payload,
    })
    if result.get('rejected'):
        reasons = result.get('reasons') or []
        event = record_human_guardian_event(
            severity='blocked' if 'secret_never_stored' in reasons else 'notice',
            title='Guardian rejected unsafe memory.',
            explanation='This looked like a password, API key, token, or secret, so AURA did not store it.' if 'secret_never_stored' in reasons else 'The memory did not meet AURA privacy or quality rules.',
            action_required='Remove secrets and save only safe preferences, workflow patterns, or non-sensitive facts.',
            run_id=run_id,
            event_type='memory_rejected',
            action='MEMORY_WRITE',
            risk='blocked' if 'secret_never_stored' in reasons else 'medium',
            context={'memory_key': key, 'reasons': reasons},
        )
        event_cb({**event, 'type': 'guardian_event', 'guardian_type': event.get('type'), 'run_id': run_id, 'status': 'blocked'})
        _send_event(event_cb, {'type': 'step_status', 'run_id': run_id, 'status': 'blocked', 'message': 'Guardian rejected this memory before storage.'})
        return {'ok': False, 'run_id': run_id, 'status': 'blocked', 'run_state': get_run_context(run_id), 'memory_result': result}
    _send_event(event_cb, {'type': 'step_status', 'run_id': run_id, 'status': 'success', 'message': 'Memory saved safely.'})
    return {'ok': True, 'run_id': run_id, 'steps': [], 'run_state': get_run_context(run_id), 'memory_result': result}


def _run_workflow_save_request(run_id: str, text: str, planning_context: dict, event_cb) -> dict | None:
    low = text.lower().strip()
    if 'reusable workflow' not in low and 'save a workflow' not in low and 'save workflow' not in low:
        return None
    workflow = create_workflow(
        name='Manual workflow suggestion',
        command_template='Reply to this email' if 'email' in low or 'reply' in low else 'Clone this repo locally',
        description='Created from the command layer for manual replay testing.',
        trigger_type='manual',
        source='command_layer',
        confidence=0.5,
        required_context=['selected_text_or_clipboard'] if 'email' in low or 'reply' in low else ['browser_url:github_repo'],
        safety_class='high',
        metadata={'created_from': text, 'context_snapshot_id': planning_context.get('snapshot_id')},
    )
    set_run_context(run_id, {
        'text': text,
        'choices': {},
        'use_macro': False,
        'status': 'done',
        'planning_context': planning_context,
        'plan': {'signature': 'workflow:save', 'goal': 'Save a replayable workflow suggestion', 'steps': []},
        'steps': [],
        'current_step_index': 0,
        'terminal_outcome': 'success',
        'approval_state': {'required': False, 'status': 'not_requested'},
        'workflow_result': workflow,
    })
    _send_event(event_cb, {'type': 'step_status', 'run_id': run_id, 'status': 'success', 'message': f"Workflow saved: {workflow['name']}."})
    return {'ok': True, 'run_id': run_id, 'steps': [], 'run_state': get_run_context(run_id), 'workflow': workflow}


def run_command(text: str, event_cb=lambda e: None, choices: dict | None = None, use_macro: bool = False, run_id: str | None = None, context: dict | None = None, proactive: dict | None = None):
    run_id = run_id or str(uuid.uuid4())
    _send_event(event_cb, {'type': 'run_start', 'run_id': run_id, 'status': 'running', 'message': text})
    planning_context = {**context, 'client_supplied': True} if context is not None else _capture_planning_context()
    identity_context = _identity_context()
    planning_context['identity'] = identity_context
    _send_event(event_cb, {'type': 'context_captured', 'run_id': run_id, 'status': 'running', 'message': 'Context snapshot captured.', 'context_snapshot_id': planning_context.get('snapshot_id')})
    special = _run_memory_request(run_id, text, planning_context, event_cb) or _run_workflow_save_request(run_id, text, planning_context, event_cb)
    if special:
        return special
    relevant_memory = _relevant_memory_for_command(text, identity_context['active_identity'])
    if relevant_memory.get('workspace_hint') and not planning_context.get('workspace_hint'):
        planning_context['workspace_hint'] = relevant_memory['workspace_hint']
    plan = plan_from_text(text, choices, planning_context)
    if plan.get('signature') == 'user_ai:web':
        privacy_check = (plan.get('context') or {}).get('privacy_check') or {}
        if privacy_check.get('requires_approval') or privacy_check.get('redacted'):
            event = record_human_guardian_event(
                severity='approval_required' if privacy_check.get('requires_approval') else 'notice',
                title='Guardian checked this external AI handoff.',
                explanation=f"Destination: {privacy_check.get('destination') or 'external AI tool'}. {privacy_check.get('approval_reason') or 'AURA prepared a privacy-checked prompt.'}",
                action_required='Review the prompt before AURA copies or pastes it into another AI tool.',
                run_id=run_id,
                event_type='external_ai_privacy_check',
                action='USER_AI_HANDOFF',
                risk='high' if privacy_check.get('requires_approval') else 'medium',
                category='tool_risk',
                approval_status='pending' if privacy_check.get('requires_approval') else 'not_required',
                context={'destination': privacy_check.get('destination'), 'labels': privacy_check.get('labels'), 'redacted': privacy_check.get('redacted'), 'identity': identity_context},
            )
            event_cb({**event, 'type': 'guardian_event', 'guardian_type': event.get('type'), 'run_id': run_id, 'status': 'awaiting_review'})
    _send_event(event_cb, {
        'type': 'memory_used',
        'run_id': run_id,
        'status': 'running',
        'message': f"Using {len(relevant_memory['items'])} relevant memories for {identity_context['identity_name']}.",
        'memory_count': len(relevant_memory['items']),
    })
    audit_payload = _signed_identity_payload(identity_context['active_identity'], {
        'identity_id': identity_context['identity_id'],
        'identity_name': identity_context['identity_name'],
        'memory_scope': identity_context['identity_scope'],
        'command': text,
        'memory_used': relevant_memory['items'],
    })
    record_audit_event({
        'run_id': run_id,
        'event_type': 'identity_action_started',
        'action_type': 'COMMAND',
        'risk_level': 'low',
        'message': f"AURA acted under {identity_context['identity_name']}.",
        'payload': audit_payload,
    })

    if plan['clarifications']:
        set_run_context(run_id, {'text': text, 'choices': choices or {}, 'use_macro': use_macro, 'status': 'needs_clarification', 'planning_context': planning_context, 'plan': {**plan, 'steps': []}})
        return {'ok': False, 'run_id': run_id, 'needs_clarification': True, 'clarifications': plan['clarifications'], 'plan': {k: v for k, v in plan.items() if k != 'steps'}}

    for key, value in (choices or {}).items():
        set_pref(key, value)
        write_memory(key, value, tags=['preference', 'choice'], importance=4)

    steps, macro = _materialize_steps(plan, use_macro)
    if macro and not use_macro:
        _send_event(event_cb, {'type': 'macro_suggested', 'run_id': run_id, 'status': 'clarification', 'message': f"Use saved workflow {macro['name']}?"})
        set_run_context(run_id, {'text': text, 'choices': choices or {}, 'use_macro': False, 'status': 'macro_suggested', 'planning_context': planning_context, 'plan': {**plan, 'steps': [s.model_dump() for s in steps]}})
        return {'ok': False, 'run_id': run_id, 'macro_suggestion': {'id': macro['id'], 'name': macro['name']}, 'plan_signature': plan['signature'], 'plan': {k: v for k, v in plan.items() if k != 'steps'}}

    set_run_context(run_id, {
        'text': text,
        'choices': choices or {},
        'use_macro': use_macro,
        'planning_context': planning_context,
        'proactive': {
            'suggestions_shown': list((proactive or {}).get('suggestions_shown', [])),
            'suggestion_selected': (proactive or {}).get('suggestion_selected'),
            'suggestion_confidence': (proactive or {}).get('suggestion_confidence'),
            'signals_used': list((proactive or {}).get('signals_used', [])),
        },
        'identity': identity_context,
        'memory_used': relevant_memory['items'],
        'steps': [s.model_dump() for s in steps],
        'plan': {**plan, 'steps': [s.model_dump() for s in steps]},
        'current_step_index': 0,
        'last_observation': {},
        'status': 'running',
        'failure_history': [],
        'repair_history': [],
        'repair_attempts': {},
        'total_repairs': 0,
        'terminal_outcome': None,
        'last_failure_class': None,
        'last_repair': None,
        'user_intervention_required': False,
        'step_history': [],
        'safety_history': [],
        'learning': {},
        'captured_context': None,
        'research_context': None,
        'draft_state': None,
        'approval_state': {'required': plan.get('assist', {}).get('target_behavior') == 'paste_back', 'status': 'not_requested'},
        'pasteback_state': {'status': 'not_started'},
        'assist': {
            'intent': plan.get('assist', {}),
            'generation': {},
            'learning_signals': {},
        },
    })

    result = execute_steps(run_id, steps, event_cb)
    last = result[-1] if result else {'status': 'done', 'step_index': len(steps) - 1}
    status = _status_from_result(result)

    ctx = get_run_context(run_id) or {}
    terminal_outcome = 'success' if status == 'done' else ('needs_user' if status == 'awaiting_approval' else ('blocked' if status == 'blocked' else (ctx.get('terminal_outcome') or 'failed')))
    update_run_context(run_id, {'status': status, 'current_step_index': last.get('step_index', 0), 'terminal_outcome': terminal_outcome})
    learning = record_run_learning(run_id, get_run_context(run_id) or {})
    update_run_context(run_id, {'learning': learning})

    if result and all(r['status'] == 'success' for r in result):
        record_macro(name=f"{plan['signature']} workflow", trigger=plan['signature'], steps=[s.model_dump() for s in plan['steps']], slots=plan.get('slots'))
        write_memory('workflow_success', plan['signature'], tags=['workflow'], importance=3)
        remember_execution(plan['signature'], 'success', plan.get('goal', text), tags=['workflow'], metadata={'run_id': run_id, 'attempts': len(result)})

    if last['status'] == 'needs_user':
        remember_execution(plan['signature'], 'blocked', _memory_detail('user_action_needed', {'run_id': run_id, 'failure_class': ctx.get('last_failure_class')}), tags=['workflow'])
        return {'ok': False, 'run_id': run_id, 'status': 'needs_user', 'resume_token': run_id, 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}

    if last['status'] == 'awaiting_approval':
        return {'ok': False, 'run_id': run_id, 'status': 'awaiting_approval', 'resume_token': run_id, 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}

    if last['status'] == 'blocked':
        remember_execution(plan['signature'], 'blocked', _memory_detail('guardian_blocked', {'run_id': run_id, 'failure_class': ctx.get('last_failure_class')}), tags=['workflow'])
        return {'ok': False, 'run_id': run_id, 'status': 'blocked', 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}

    if status != 'done':
        remember_execution(plan['signature'], 'failure', _memory_detail('terminal_failure', {'run_id': run_id, 'failure_class': ctx.get('last_failure_class'), 'terminal_outcome': terminal_outcome}), tags=['workflow'])
    return {'ok': status == 'done', 'run_id': run_id, 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}


def resume_run(run_id: str, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'run_id': run_id, 'error': 'run_not_found'}

    steps = [Step(**s) for s in ctx.get('steps', [])]
    start_index = int(ctx.get('paused_step_index', ctx.get('current_step_index', 0)))
    _send_event(event_cb, {'type': 'resumed', 'run_id': run_id, 'status': 'running', 'message': 'Run resumed by user', 'url': (ctx.get('last_observation') or {}).get('url', '')})

    result = execute_steps(run_id, steps, event_cb, start_index=start_index)
    if result and result[-1]['status'] == 'needs_user':
        learning = record_run_learning(run_id, get_run_context(run_id) or {})
        update_run_context(run_id, {'learning': learning})
        return {'ok': False, 'run_id': run_id, 'status': 'needs_user', 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}
    if result and result[-1]['status'] == 'awaiting_approval':
        learning = record_run_learning(run_id, get_run_context(run_id) or {})
        update_run_context(run_id, {'learning': learning, 'status': 'awaiting_approval'})
        return {'ok': False, 'run_id': run_id, 'status': 'awaiting_approval', 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}

    status = _status_from_result(result)
    terminal_outcome = 'success' if status == 'done' else ((get_run_context(run_id) or {}).get('terminal_outcome') or 'failed')
    update_run_context(run_id, {'status': status, 'terminal_outcome': terminal_outcome, 'paused': False})
    learning = record_run_learning(run_id, get_run_context(run_id) or {})
    update_run_context(run_id, {'learning': learning})
    return {'ok': status == 'done', 'run_id': run_id, 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}


def approve_assist_run(run_id: str, approved_text: str | None = None, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'error': 'run_not_found', 'run_id': run_id}
    approval = {**(ctx.get('approval_state') or {})}
    generated_text = approval.get('draft_text') or ''
    final_text = approved_text or generated_text
    task_kind = (ctx.get('plan') or {}).get('assist', {}).get('task_kind')
    if final_text != generated_text:
        approval['edited_text'] = approved_text or ''
        if len(final_text) > len(generated_text) * 1.3:
            apply_feedback_preferences('more detail', task_kind)
        elif generated_text and len(final_text) < len(generated_text) * 0.8:
            apply_feedback_preferences('more concise', task_kind)
    if (ctx.get('research_context') or {}).get('search_used'):
        set_pref(f'assist.{task_kind}.research', 'prefer')
        write_memory(f'assist.{task_kind}.research', 'prefer', tags=['preference', 'assist', 'research'], importance=4)
    approval.update({'status': 'approved', 'final_text': final_text, 'approved_by_user': True, 'decided_at': time.time()})
    update_run_context(run_id, {'approval_state': approval, 'status': 'approved_pending_paste', 'paused': False, 'user_intervention_required': False})
    update_run_context(run_id, {'assist': {**(ctx.get('assist') or {}), 'final_outcome': 'approved_pending_paste'}})
    _send_event(event_cb, {'type': 'approval_received', 'run_id': run_id, 'status': 'approved', 'message': 'Draft approved for paste-back.'})
    return resume_run(run_id, event_cb)


def approve_run(run_id: str, approved_text: str | None = None, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'error': 'run_not_found', 'run_id': run_id}
    approval = ctx.get('approval_state') or {}
    if approval.get('kind') != 'tool_confirmation':
        return approve_assist_run(run_id, approved_text, event_cb)

    decision = decide_approval(run_id, True, {'approved_by_user': True, 'approved_text': approved_text or ''})
    if not decision:
        return {'ok': False, 'error': 'approval_not_found', 'run_id': run_id}
    approval.update({'status': 'approved', 'approved_by_user': True, 'decided_at': time.time()})
    update_run_context(run_id, {'approval_state': approval, 'status': 'approved_pending_resume', 'paused': False, 'user_intervention_required': False})
    _send_event(event_cb, {
        'type': 'approval_received',
        'run_id': run_id,
        'status': 'approved',
        'approval_id': decision.get('approval_id'),
        'step_id': decision.get('step_id'),
        'message': 'Risky action approved; resuming run.',
    })
    return resume_run(run_id, event_cb)


def retry_assist_run(run_id: str, feedback: str | None = None, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'error': 'run_not_found', 'run_id': run_id}
    task_kind = (ctx.get('plan') or {}).get('assist', {}).get('task_kind')
    learned = apply_feedback_preferences(feedback, task_kind)
    try:
        draft = draft_from_state(ctx, feedback=feedback)
    except RuntimeError as exc:
        update_run_context(run_id, {'status': 'needs_user', 'last_failure_class': 'assist_model_unavailable', 'assist': {**(ctx.get('assist') or {}), 'learning_signals': {'feedback_preferences': learned}}})
        _send_event(event_cb, {'type': 'needs_user', 'run_id': run_id, 'status': 'needs_user', 'message': str(exc)})
        return {'ok': False, 'run_id': run_id, 'status': 'needs_user', 'run_state': get_run_context(run_id)}
    approval = {**(ctx.get('approval_state') or {})}
    approval.update({'status': 'pending', 'draft_text': draft['draft_text'], 'edited_text': '', 'final_text': '', 'feedback': feedback or '', 'approved_by_user': False, 'requested_at': time.time()})
    update_run_context(run_id, {'draft_state': draft, 'approval_state': approval, 'status': 'awaiting_approval', 'paused': True, 'assist': {**(ctx.get('assist') or {}), 'learning_signals': {'feedback_preferences': learned}, 'final_outcome': 'awaiting_approval'}})
    _send_event(event_cb, {'type': 'draft_regenerated', 'run_id': run_id, 'status': 'awaiting_approval', 'message': 'Draft regenerated for review.'})
    learning = record_run_learning(run_id, get_run_context(run_id) or {})
    update_run_context(run_id, {'learning': learning})
    return {'ok': True, 'run_id': run_id, 'status': 'awaiting_approval', 'run_state': get_run_context(run_id)}


def reject_assist_run(run_id: str, reason: str | None = None, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'error': 'run_not_found', 'run_id': run_id}
    task_kind = (ctx.get('plan') or {}).get('assist', {}).get('task_kind')
    learned = apply_feedback_preferences(reason, task_kind)
    if (ctx.get('research_context') or {}).get('search_used') and reason and 'not needed' in reason.lower():
        set_pref(f'assist.{task_kind}.research', 'avoid')
        write_memory(f'assist.{task_kind}.research', 'avoid', tags=['preference', 'assist', 'research'], importance=4)
    approval = {**(ctx.get('approval_state') or {})}
    approval.update({'status': 'rejected', 'decision_reason': reason or '', 'decided_at': time.time(), 'approved_by_user': False})
    update_run_context(run_id, {'approval_state': approval, 'status': 'rejected', 'terminal_outcome': 'rejected', 'paused': False, 'pasteback_state': {'status': 'skipped', 'paste_attempted': False, 'paste_blocked_reason': 'draft_rejected'}, 'assist': {**(ctx.get('assist') or {}), 'learning_signals': {'feedback_preferences': learned}, 'final_outcome': 'rejected'}})
    _send_event(event_cb, {'type': 'draft_rejected', 'run_id': run_id, 'status': 'rejected', 'message': 'Draft rejected; paste-back skipped.'})
    learning = record_run_learning(run_id, get_run_context(run_id) or {})
    update_run_context(run_id, {'learning': learning})
    return {'ok': True, 'run_id': run_id, 'status': 'rejected', 'run_state': get_run_context(run_id)}


def reject_run(run_id: str, reason: str | None = None, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'error': 'run_not_found', 'run_id': run_id}
    approval = ctx.get('approval_state') or {}
    if approval.get('kind') != 'tool_confirmation':
        return reject_assist_run(run_id, reason, event_cb)

    decision = decide_approval(run_id, False, {'approved_by_user': False, 'reason': reason or ''})
    if not decision:
        return {'ok': False, 'error': 'approval_not_found', 'run_id': run_id}
    approval.update({'status': 'rejected', 'approved_by_user': False, 'decision_reason': reason or '', 'decided_at': time.time()})
    update_run_context(run_id, {
        'approval_state': approval,
        'status': 'rejected',
        'terminal_outcome': 'rejected',
        'paused': False,
        'user_intervention_required': False,
    })
    _send_event(event_cb, {
        'type': 'approval_rejected',
        'run_id': run_id,
        'status': 'rejected',
        'approval_id': decision.get('approval_id'),
        'step_id': decision.get('step_id'),
        'message': 'Risky action rejected; run stopped.',
    })
    learning = record_run_learning(run_id, get_run_context(run_id) or {})
    update_run_context(run_id, {'learning': learning})
    return {'ok': True, 'run_id': run_id, 'status': 'rejected', 'run_state': get_run_context(run_id)}
