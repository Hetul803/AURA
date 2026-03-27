from __future__ import annotations

import json
import time
import uuid

from .assist import apply_feedback_preferences, draft_from_state
from .executor import execute_steps
from .learning import record_run_learning
from .macros import match_macro, record_macro, render_macro_steps, touch_macro
from .memory import remember_execution, write_memory
from .planner import plan_from_text
from .prefs import set_pref
from .state import get_run_context, set_run_context, update_run_context
from .steps import Step


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
    return 'done' if all(r['status'] == 'success' for r in result) else 'partial'


def run_command(text: str, event_cb=lambda e: None, choices: dict | None = None, use_macro: bool = False, run_id: str | None = None):
    run_id = run_id or str(uuid.uuid4())
    event_cb({'type': 'run_start', 'run_id': run_id, 'status': 'running', 'message': text})
    plan = plan_from_text(text, choices)

    if plan['clarifications']:
        set_run_context(run_id, {'text': text, 'choices': choices or {}, 'use_macro': use_macro, 'status': 'needs_clarification', 'plan': {**plan, 'steps': []}})
        return {'ok': False, 'run_id': run_id, 'needs_clarification': True, 'clarifications': plan['clarifications'], 'plan': {k: v for k, v in plan.items() if k != 'steps'}}

    for key, value in (choices or {}).items():
        set_pref(key, value)
        write_memory(key, value, tags=['preference', 'choice'], importance=4)

    steps, macro = _materialize_steps(plan, use_macro)
    if macro and not use_macro:
        event_cb({'type': 'macro_suggested', 'run_id': run_id, 'status': 'clarification', 'message': f"Use saved workflow {macro['name']}?"})
        set_run_context(run_id, {'text': text, 'choices': choices or {}, 'use_macro': False, 'status': 'macro_suggested', 'plan': {**plan, 'steps': [s.model_dump() for s in steps]}})
        return {'ok': False, 'run_id': run_id, 'macro_suggestion': {'id': macro['id'], 'name': macro['name']}, 'plan_signature': plan['signature'], 'plan': {k: v for k, v in plan.items() if k != 'steps'}}

    set_run_context(run_id, {
        'text': text,
        'choices': choices or {},
        'use_macro': use_macro,
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
    terminal_outcome = ctx.get('terminal_outcome') or ('success' if status == 'done' else ('needs_user' if status == 'awaiting_approval' else 'failed'))
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

    if status != 'done':
        remember_execution(plan['signature'], 'failure', _memory_detail('terminal_failure', {'run_id': run_id, 'failure_class': ctx.get('last_failure_class'), 'terminal_outcome': terminal_outcome}), tags=['workflow'])
    return {'ok': status == 'done', 'run_id': run_id, 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}


def resume_run(run_id: str, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'run_id': run_id, 'error': 'run_not_found'}

    steps = [Step(**s) for s in ctx.get('steps', [])]
    start_index = int(ctx.get('paused_step_index', ctx.get('current_step_index', 0)))
    event_cb({'type': 'resumed', 'run_id': run_id, 'status': 'running', 'message': 'Run resumed by user', 'url': (ctx.get('last_observation') or {}).get('url', '')})

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
    event_cb({'type': 'approval_received', 'run_id': run_id, 'status': 'approved', 'message': 'Draft approved for paste-back.'})
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
        event_cb({'type': 'needs_user', 'run_id': run_id, 'status': 'needs_user', 'message': str(exc)})
        return {'ok': False, 'run_id': run_id, 'status': 'needs_user', 'run_state': get_run_context(run_id)}
    approval = {**(ctx.get('approval_state') or {})}
    approval.update({'status': 'pending', 'draft_text': draft['draft_text'], 'edited_text': '', 'final_text': '', 'feedback': feedback or '', 'approved_by_user': False, 'requested_at': time.time()})
    update_run_context(run_id, {'draft_state': draft, 'approval_state': approval, 'status': 'awaiting_approval', 'paused': True, 'assist': {**(ctx.get('assist') or {}), 'learning_signals': {'feedback_preferences': learned}, 'final_outcome': 'awaiting_approval'}})
    event_cb({'type': 'draft_regenerated', 'run_id': run_id, 'status': 'awaiting_approval', 'message': 'Draft regenerated for review.'})
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
    event_cb({'type': 'draft_rejected', 'run_id': run_id, 'status': 'rejected', 'message': 'Draft rejected; paste-back skipped.'})
    learning = record_run_learning(run_id, get_run_context(run_id) or {})
    update_run_context(run_id, {'learning': learning})
    return {'ok': True, 'run_id': run_id, 'status': 'rejected', 'run_state': get_run_context(run_id)}
