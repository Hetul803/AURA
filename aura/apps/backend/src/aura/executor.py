from __future__ import annotations
import time
from .safety import guard_step
from tools.web_playwright import handle_web_action
from tools.os_automation import handle_os_action, read_clipboard
from .state import is_run_cancelled, set_run_context, get_run_context, record_safety_event


def _condition_ok(cond, observation: dict) -> bool:
    typ = cond.type
    key = cond.key
    expected = cond.expected
    val = observation.get(key)
    if typ in ('equals', 'url_equals'):
        return val == expected
    if typ in ('contains', 'url_contains', 'title_contains'):
        return isinstance(val, str) and str(expected) in val
    if typ == 'gte':
        try:
            return float(val) >= float(expected)
        except Exception:
            return False
    if typ == 'bool':
        return bool(val) is bool(expected)
    return True


def _check_conditions(step, observation: dict, which: str):
    checks = step.preconditions if which == 'pre' else step.postconditions
    return all(_condition_ok(c, observation) for c in checks)


def execute_steps(run_id: str, steps, event_cb, wait_poll_ms: int = 100, start_index: int = 0):
    out = []
    for idx, step in enumerate(steps[start_index:], start=start_index):
        if is_run_cancelled(run_id):
            event_cb({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
            return out + [{'step': step.id, 'status': 'cancelled', 'step_index': idx}]
        event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'name': step.name, 'safety_level': step.safety_level, 'status': 'planned', 'timestamp': time.time()})
        event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'name': step.name, 'safety_level': step.safety_level, 'status': 'running', 'timestamp': time.time()})

        ctx = get_run_context(run_id) or {}
        obs = ctx.get('last_observation', {})
        if not _check_conditions(step, obs, 'pre'):
            out.append({'step': step.id, 'status': 'failed_precondition', 'step_index': idx})
            event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'status': 'fail', 'message': 'precondition failed', 'timestamp': time.time(), 'url': obs.get('url', '')})
            continue

        guard = guard_step(step)
        if guard == 'blocked':
            out.append({'step': step.id, 'status': 'blocked', 'step_index': idx})
            record_safety_event({'kind':'blocked','run_id':run_id,'step_id':step.id,'action':step.action_type})
            event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'status': 'failed', 'message': 'blocked by safety', 'timestamp': time.time(), 'url': obs.get('url', '')})
            continue
        if guard == 'confirm':
            out.append({'step': step.id, 'status': 'needs_confirmation', 'step_index': idx})
            record_safety_event({'kind':'confirmation','run_id':run_id,'step_id':step.id,'action':step.action_type})
            event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'status': 'clarification', 'message': 'confirmation required', 'timestamp': time.time(), 'url': obs.get('url', '')})
            continue

        res = None
        for _ in range(step.retry_policy.max_retries + 1):
            if step.action_type == 'WAIT_FOR':
                target_ms = int(step.args.get('ms', 1000))
                elapsed = 0
                while elapsed < target_ms:
                    if is_run_cancelled(run_id):
                        event_cb({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
                        return out + [{'step': step.id, 'status': 'cancelled', 'step_index': idx}]
                    time.sleep(wait_poll_ms / 1000)
                    elapsed += wait_poll_ms
                res = {'ok': True, 'waited_ms': target_ms, 'observation': obs}
            elif step.action_type.startswith('OS_') or step.action_type in ('TAKE_SCREENSHOT',):
                if step.action_type == 'OS_PASTE' and not step.args.get('text'):
                    clip = read_clipboard()
                    step.args['text'] = clip.get('text', '')
                res = handle_os_action(step)
                if step.action_type in ('OS_PASTE','OS_WRITE_CLIPBOARD','OS_COPY_SELECTION'):
                    record_safety_event({'kind':'clipboard','run_id':run_id,'step_id':step.id,'action':step.action_type,'ok':res.get('ok',False)})
                res['observation'] = {**obs, **{k: v for k, v in res.items() if k in ('active_app','window_title')}}
            else:
                if step.args.get('query') == '__FROM_CLIPBOARD__':
                    clip = read_clipboard()
                    step.args['query'] = clip.get('text', '')
                res = handle_web_action(step)
                if step.action_type == 'WEB_UPLOAD':
                    record_safety_event({'kind':'upload','run_id':run_id,'step_id':step.id,'ok':res.get('ok',False),'file_path':step.args.get('file_path')})
            if res.get('ok'):
                break
            if res.get('error') == 'user_action_needed':
                step_obs = res.get('observation', obs)
                set_run_context(run_id, {**ctx, 'paused': True, 'paused_step_index': idx, 'last_observation': step_obs})
                event_cb({'type': 'needs_user', 'run_id': run_id, 'status': 'needs_user', 'step_id': step.id, 'step_index': idx, 'message': res.get('message', 'User action required'), 'url': step_obs.get('url', ''), 'session': 'login_required'})
                return out + [{'step': step.id, 'status': 'needs_user', 'result': res, 'step_index': idx}]
            time.sleep(step.retry_policy.backoff_ms / 1000)

        step_obs = (res or {}).get('observation', obs)
        ctx = get_run_context(run_id) or {}
        set_run_context(run_id, {**ctx, 'last_observation': step_obs, 'current_step_index': idx})

        status = 'success' if (res and res.get('ok') and _check_conditions(step, step_obs, 'post')) else 'fail'
        out.append({'step': step.id, 'status': status, 'result': res, 'step_index': idx})
        event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'status': status, 'timestamp': time.time(), 'message': '' if status == 'success' else str(res), 'url': step_obs.get('url', ''), 'session': 'active' if not step_obs.get('login_required') else 'login_required'})

    event_cb({'type': 'run_done', 'run_id': run_id, 'status': 'done', 'timestamp': time.time()})
    return out
