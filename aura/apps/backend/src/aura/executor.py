from __future__ import annotations
import time
from .safety import guard_step
from tools.web_playwright import handle_web_action
from .state import is_run_cancelled


def execute_steps(run_id: str, steps, event_cb, wait_poll_ms: int = 100, start_index: int = 0):
    out = []
    for idx, step in enumerate(steps[start_index:], start=start_index):
        if is_run_cancelled(run_id):
            event_cb({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
            return out + [{'step': step.id, 'status': 'cancelled', 'step_index': idx}]
        event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'name': step.name, 'safety_level': step.safety_level, 'status': 'planned', 'timestamp': time.time()})
        event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'name': step.name, 'safety_level': step.safety_level, 'status': 'running', 'timestamp': time.time()})

        guard = guard_step(step)
        if guard == 'blocked':
            out.append({'step': step.id, 'status': 'blocked', 'step_index': idx})
            event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'status': 'failed', 'message': 'blocked by safety', 'timestamp': time.time()})
            continue
        if guard == 'confirm':
            out.append({'step': step.id, 'status': 'needs_confirmation', 'step_index': idx})
            event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'status': 'clarification', 'message': 'confirmation required', 'timestamp': time.time()})
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
                res = {'ok': True, 'waited_ms': target_ms}
            else:
                res = handle_web_action(step)
            if res.get('ok'):
                break
            if res.get('error') == 'user_action_needed':
                event_cb({'type': 'needs_user', 'run_id': run_id, 'status': 'needs_user', 'step_id': step.id, 'step_index': idx, 'message': res.get('message', 'User action required')})
                return out + [{'step': step.id, 'status': 'needs_user', 'result': res, 'step_index': idx}]
            time.sleep(step.retry_policy.backoff_ms / 1000)
        status = 'success' if (res and res.get('ok')) else 'fail'
        out.append({'step': step.id, 'status': status, 'result': res, 'step_index': idx})
        event_cb({'type': 'step_status', 'run_id': run_id, 'step_id': step.id, 'status': status, 'timestamp': time.time(), 'message': '' if status == 'success' else str(res)})
    event_cb({'type': 'run_done', 'run_id': run_id, 'status': 'done', 'timestamp': time.time()})
    return out
