from __future__ import annotations
import uuid
from .planner import plan_from_text
from .executor import execute_steps
from .macros import match_macro, record_macro, render_macro_steps, touch_macro
from .prefs import set_pref
from .memory import write_memory
from .steps import Step
from .state import set_run_context, get_run_context


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
        set_run_context(run_id, {'text': text, 'choices': choices or {}, 'use_macro': use_macro, 'status': 'needs_clarification'})
        return {'ok': False, 'run_id': run_id, 'needs_clarification': True, 'clarifications': plan['clarifications']}

    for key, value in (choices or {}).items():
        set_pref(key, value)
        write_memory(key, value, tags=['preference', 'choice'], importance=4)

    steps, macro = _materialize_steps(plan, use_macro)
    if macro and not use_macro:
        event_cb({'type': 'macro_suggested', 'run_id': run_id, 'status': 'clarification', 'message': f"Use saved workflow {macro['name']}?"})
        set_run_context(run_id, {'text': text, 'choices': choices or {}, 'use_macro': False, 'status': 'macro_suggested'})
        return {'ok': False, 'run_id': run_id, 'macro_suggestion': {'id': macro['id'], 'name': macro['name']}, 'plan_signature': plan['signature']}

    result = execute_steps(run_id, steps, event_cb)
    last = result[-1] if result else {'status': 'done'}
    status = 'needs_user' if last['status'] == 'needs_user' else ('done' if all(r['status'] == 'success' for r in result) else 'partial')
    set_run_context(run_id, {'text': text, 'choices': choices or {}, 'use_macro': use_macro, 'status': status, 'step_index': last.get('step_index', 0)})

    if result and all(r['status'] == 'success' for r in result):
        record_macro(name=f"{plan['signature']} workflow", trigger=plan['signature'], steps=[s.model_dump() for s in plan['steps']], slots=plan.get('slots'))
        write_memory('workflow_success', plan['signature'], tags=['workflow'], importance=3)

    if last['status'] == 'needs_user':
        return {'ok': False, 'run_id': run_id, 'status': 'needs_user', 'resume_token': run_id, 'steps': result}
    return {'ok': True, 'run_id': run_id, 'steps': result}


def resume_run(run_id: str, event_cb=lambda e: None):
    ctx = get_run_context(run_id)
    if not ctx:
        return {'ok': False, 'run_id': run_id, 'error': 'run_not_found'}
    event_cb({'type': 'resumed', 'run_id': run_id, 'status': 'running', 'message': 'Run resumed by user'})
    return run_command(ctx['text'], event_cb, ctx.get('choices', {}), ctx.get('use_macro', False), run_id=run_id)
