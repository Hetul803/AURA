from __future__ import annotations

import time
from copy import deepcopy

from . import observer
from .safety import guard_step
from .state import is_run_cancelled, set_run_context, get_run_context, record_safety_event
from tools.code_runner import classify_failure
from tools.os_automation import read_clipboard
from tools.tool_router import dispatch_tool_action



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



def _expected_outcome_met(step, result: dict, observation_map: dict) -> bool:
    expected = step.expected_outcome or {}
    if not expected:
        return result.get('ok', False)
    for key, exp in expected.items():
        if key == 'exit_code' and observation_map.get('exit_code') != exp:
            return False
        if key == 'exists' and bool(result.get('exists', observation_map.get('file_exists'))) != bool(exp):
            return False
        if key == 'url_contains' and exp not in str(observation_map.get('url', '')):
            return False
        if key == 'active_app_contains' and exp.lower() not in str(observation_map.get('active_app', '')).lower():
            return False
        if key == 'written_gte' and int(result.get('written', 0)) < int(exp):
            return False
        if key == 'pasted_gte' and int(result.get('pasted', 0)) < int(exp):
            return False
        if key == 'clipboard_length_gte' and int(observation_map.get('clipboard_length', 0)) < int(exp):
            return False
        if key == 'key_points_gte' and len(result.get('key_points', [])) < int(exp):
            return False
        if key == 'flights_gte' and len(result.get('flights', [])) < int(exp):
            return False
        if key == 'unread_count_gte' and int(result.get('unread_count', 0)) < int(exp):
            return False
        if key == 'opened_path' and str(result.get('opened_path', result.get('path', ''))) != str(exp):
            return False
        if key == 'ok' and bool(result.get('ok')) != bool(exp):
            return False
    return result.get('ok', False)



def _build_repair_step(step, result: dict, attempt: int):
    if step.fallback_hint == 'repair_python_and_retry' and step.action_type == 'CODE_RUN':
        observation_map = result.get('observation') or {}
        failure_info = classify_failure(observation_map.get('stderr', ''), observation_map.get('stdout', ''))
        return {
            'id': f'{step.id}:repair:{attempt}',
            'name': f'Repair {step.name}',
            'action_type': 'CODE_REPAIR',
            'tool': 'code',
            'args': {
                'path': step.args.get('path', ''),
                'error': result.get('error'),
                'observation': observation_map,
                'failure_class': failure_info.get('failure_class'),
            },
        }
    return None



def _emit_step(event_cb, run_id: str, step, status: str, **extra):
    payload = {
        'type': 'step_status',
        'run_id': run_id,
        'step_id': step.id,
        'name': step.name,
        'safety_level': step.safety_level,
        'status': status,
        'timestamp': time.time(),
    }
    payload.update(extra)
    event_cb(payload)



def execute_steps(run_id: str, steps, event_cb, wait_poll_ms: int = 100, start_index: int = 0):
    out = []
    for idx, step in enumerate(steps[start_index:], start=start_index):
        if is_run_cancelled(run_id):
            event_cb({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
            return out + [{'step': step.id, 'status': 'cancelled', 'step_index': idx}]

        ctx = get_run_context(run_id) or {}
        last_obs = ctx.get('last_observation', {})
        if not _check_conditions(step, last_obs, 'pre'):
            out.append({'step': step.id, 'status': 'failed_precondition', 'step_index': idx})
            _emit_step(event_cb, run_id, step, 'fail', message='precondition failed', url=last_obs.get('url', ''))
            continue

        guard = guard_step(step)
        if guard == 'blocked':
            out.append({'step': step.id, 'status': 'blocked', 'step_index': idx})
            record_safety_event({'kind': 'blocked', 'run_id': run_id, 'step_id': step.id, 'action': step.action_type})
            _emit_step(event_cb, run_id, step, 'failed', message='blocked by safety', url=last_obs.get('url', ''))
            continue
        if guard == 'confirm':
            out.append({'step': step.id, 'status': 'needs_confirmation', 'step_index': idx})
            record_safety_event({'kind': 'confirmation', 'run_id': run_id, 'step_id': step.id, 'action': step.action_type})
            _emit_step(event_cb, run_id, step, 'clarification', message='confirmation required', url=last_obs.get('url', ''))
            continue

        _emit_step(event_cb, run_id, step, 'planned')
        attempts = 0
        max_attempts = step.retry_policy.max_retries + 1
        final_result = None
        final_status = 'fail'

        while attempts < max_attempts:
            if is_run_cancelled(run_id):
                event_cb({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
                return out + [{'step': step.id, 'status': 'cancelled', 'step_index': idx}]

            _emit_step(event_cb, run_id, step, 'running', attempt=attempts + 1)
            step_to_run = deepcopy(step)
            if step_to_run.action_type == 'WAIT_FOR':
                target_ms = int(step_to_run.args.get('ms', 1000))
                elapsed = 0
                while elapsed < target_ms:
                    if is_run_cancelled(run_id):
                        event_cb({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
                        return out + [{'step': step.id, 'status': 'cancelled', 'step_index': idx}]
                    time.sleep(wait_poll_ms / 1000)
                    elapsed += wait_poll_ms
                result = {'ok': True, 'status': 'success', 'action': 'WAIT_FOR', 'result': {'waited_ms': target_ms}, 'observation': last_obs, 'retryable': False, 'requires_user': False, 'safety_flags': [], 'artifacts': []}
            else:
                if step_to_run.action_type == 'OS_PASTE' and not step_to_run.args.get('text'):
                    clip = read_clipboard()
                    step_to_run.args['text'] = clip.get('text', '')
                if step_to_run.args.get('query') == '__FROM_CLIPBOARD__':
                    clip = read_clipboard()
                    step_to_run.args['query'] = clip.get('text', '')
                result = dispatch_tool_action(step_to_run)

            observation_map = observer.normalize_tool_observation(result, last_obs)
            ctx = get_run_context(run_id) or {}
            set_run_context(run_id, {**ctx, 'last_observation': observation_map, 'current_step_index': idx})

            if step.action_type in ('OS_PASTE', 'OS_WRITE_CLIPBOARD', 'OS_COPY_SELECTION'):
                record_safety_event({'kind': 'clipboard', 'run_id': run_id, 'step_id': step.id, 'action': step.action_type, 'ok': result.get('ok', False)})
            if step.action_type == 'WEB_UPLOAD':
                record_safety_event({'kind': 'upload', 'run_id': run_id, 'step_id': step.id, 'ok': result.get('ok', False), 'file_path': step.args.get('file_path')})

            if result.get('requires_user'):
                set_run_context(run_id, {**ctx, 'paused': True, 'paused_step_index': idx, 'last_observation': observation_map})
                event_cb({'type': 'needs_user', 'run_id': run_id, 'status': 'needs_user', 'step_id': step.id, 'step_index': idx, 'message': result.get('error') or 'User action required', 'url': observation_map.get('url', ''), 'session': 'login_required'})
                return out + [{'step': step.id, 'status': 'needs_user', 'result': result, 'step_index': idx}]

            if _expected_outcome_met(step, result, observation_map) and _check_conditions(step, observation_map, 'post'):
                final_result = result
                final_status = 'success'
                break

            repair_step = _build_repair_step(step, result, attempts)
            if repair_step:
                _emit_step(event_cb, run_id, step, 'repairing', message=repair_step['name'])
                repair_result = dispatch_tool_action(type('RepairStep', (), repair_step)())
                repair_observation = observer.normalize_tool_observation(repair_result, observation_map)
                set_run_context(run_id, {**ctx, 'last_observation': repair_observation, 'current_step_index': idx})
                if repair_result.get('ok'):
                    remember = f"{repair_result.get('result', {}).get('repair', 'repair applied')}"
                    from .memory import remember_execution
                    remember_execution(f"script:{step.args.get('path', '')}", 'repair', remember, tags=['code'])
                    attempts += 1
                    last_obs = repair_observation
                    time.sleep(step.retry_policy.backoff_ms / 1000)
                    continue
                final_result = repair_result
                final_status = 'fail'
                break

            final_result = result
            final_status = 'fail'
            if not result.get('retryable'):
                break
            attempts += 1
            last_obs = observation_map
            time.sleep(step.retry_policy.backoff_ms / 1000)

        final_observation = observer.normalize_tool_observation(final_result or {}, last_obs)
        out.append({'step': step.id, 'status': final_status, 'result': final_result, 'step_index': idx})
        _emit_step(
            event_cb,
            run_id,
            step,
            final_status,
            message='' if final_status == 'success' else str((final_result or {}).get('error') or final_result),
            url=final_observation.get('url', ''),
            session='active' if not final_observation.get('login_required') else 'login_required',
        )

    event_cb({'type': 'run_done', 'run_id': run_id, 'status': 'done', 'timestamp': time.time()})
    return out
