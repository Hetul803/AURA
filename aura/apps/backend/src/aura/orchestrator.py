from __future__ import annotations
import uuid
from .planner import plan_from_text
from .executor import execute_steps
from .macros import match_macro, record_macro, render_macro_steps, touch_macro
from .prefs import set_pref
from .memory import write_memory
from .steps import Step


def run_command(text: str, event_cb=lambda e: None, choices: dict | None = None, use_macro: bool = False):
    run_id = str(uuid.uuid4())
    event_cb({'type': 'run_start', 'run_id': run_id, 'status': 'running', 'message': text})
    plan = plan_from_text(text, choices)

    if plan['clarifications']:
        return {'ok': False, 'run_id': run_id, 'needs_clarification': True, 'clarifications': plan['clarifications']}

    for key, value in (choices or {}).items():
        set_pref(key, value)
        write_memory(key, value, tags=['preference', 'choice'], importance=4)

    macro = match_macro(plan['signature'])
    if macro and not use_macro:
        event_cb({'type': 'macro_suggested', 'run_id': run_id, 'status': 'clarification', 'message': f"Use saved workflow {macro['name']}?"})
        return {'ok': False, 'run_id': run_id, 'macro_suggestion': {'id': macro['id'], 'name': macro['name']}, 'plan_signature': plan['signature']}

    steps = plan['steps']
    if macro and use_macro:
        steps = [Step(**s) for s in render_macro_steps(macro, plan.get('slots'))]
        touch_macro(macro['id'])

    result = execute_steps(run_id, steps, event_cb)
    if result and all(r['status'] == 'success' for r in result):
        record_macro(name=f"{plan['signature']} workflow", trigger=plan['signature'], steps=[s.model_dump() for s in plan['steps']], slots=plan.get('slots'))
        write_memory('workflow_success', plan['signature'], tags=['workflow'], importance=3)

    return {'ok': True, 'run_id': run_id, 'steps': result}
