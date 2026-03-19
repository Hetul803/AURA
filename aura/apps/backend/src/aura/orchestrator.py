from __future__ import annotations

import json
import uuid

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
    })

    result = execute_steps(run_id, steps, event_cb)
    last = result[-1] if result else {'status': 'done', 'step_index': len(steps) - 1}
    status = 'needs_user' if last['status'] == 'needs_user' else ('done' if all(r['status'] == 'success' for r in result) else 'partial')

    ctx = get_run_context(run_id) or {}
    terminal_outcome = ctx.get('terminal_outcome') or ('success' if status == 'done' else 'failed')
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

    if status != 'done':
        remember_execution(
            plan['signature'],
            'failure',
            _memory_detail('terminal_failure', {'run_id': run_id, 'failure_class': ctx.get('last_failure_class'), 'terminal_outcome': terminal_outcome}),
            tags=['workflow'],
        )
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

    status = 'done' if result and all(step['status'] == 'success' for step in result) else 'partial'
    terminal_outcome = 'success' if status == 'done' else ((get_run_context(run_id) or {}).get('terminal_outcome') or 'failed')
    update_run_context(run_id, {'status': status, 'terminal_outcome': terminal_outcome})
    learning = record_run_learning(run_id, get_run_context(run_id) or {})
    update_run_context(run_id, {'learning': learning})
    return {'ok': status == 'done', 'run_id': run_id, 'steps': result, 'plan': ctx.get('plan'), 'run_state': get_run_context(run_id)}
