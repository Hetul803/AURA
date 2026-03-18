from __future__ import annotations

import uuid

from .executor import execute_steps
from .macros import match_macro, record_macro, render_macro_steps, touch_macro
from .memory import write_memory, remember_execution
from .planner import plan_from_text
from .prefs import set_pref
from .state import set_run_context, get_run_context
from .steps import Step



def _materialize_steps(plan: dict, use_macro: bool = False):
    macro = match_macro(plan['signature'])
    if macro and use_macro:
        touch_macro(macro['id'])
        return [Step(**s) for s in render_macro_steps(macro, plan.get('slots'))], macro
    return plan['steps'], macro



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
    })

    result = execute_steps(run_id, steps, event_cb)
    last = result[-1] if result else {'status': 'done', 'step_index': len(steps) - 1}
    status = 'needs_user' if last['status'] == 'needs_user' else ('done' if all(r['status'] == 'success' for r in result) else 'partial')

    ctx = get_run_context(run_id) or {}
    set_run_context(run_id, {**ctx, 'status': status, 'current_step_index': last.get('step_index', 0)})

    if result and all(r['status'] == 'success' for r in result):
        record_macro(name=f"{plan['signature']} workflow", trigger=plan['signature'], steps=[s.model_dump() for s in plan['steps']], slots=plan.get('slots'))
        write_memory('workflow_success', plan['signature'], tags=['workflow'], importance=3)
        remember_execution(plan['signature'], 'success', plan.get('goal', text), tags=['workflow'])

    if last['status'] == 'needs_user':
        remember_execution(plan['signature'], 'blocked', str(last.get('result', {}).get('error', 'user_action_needed')), tags=['workflow'])
        return {'ok': False, 'run_id': run_id, 'status': 'needs_user', 'resume_token': run_id, 'steps': result, 'plan': ctx.get('plan')}

    if status != 'done':
        remember_execution(plan['signature'], 'failure', str(last.get('result', {}).get('error', 'step_failed')), tags=['workflow'])
    return {'ok': status == 'done', 'run_id': run_id, 'steps': result, 'plan': ctx.get('plan')}



def resume_run(run_id: str, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'run_id': run_id, 'error': 'run_not_found'}

    steps = [Step(**s) for s in ctx.get('steps', [])]
    start_index = int(ctx.get('paused_step_index', ctx.get('current_step_index', 0)))
    event_cb({'type': 'resumed', 'run_id': run_id, 'status': 'running', 'message': 'Run resumed by user', 'url': (ctx.get('last_observation') or {}).get('url', '')})

    result = execute_steps(run_id, steps, event_cb, start_index=start_index)
    if result and result[-1]['status'] == 'needs_user':
        return {'ok': False, 'run_id': run_id, 'status': 'needs_user', 'steps': result, 'plan': ctx.get('plan')}
    return {'ok': True, 'run_id': run_id, 'steps': result, 'plan': ctx.get('plan')}
