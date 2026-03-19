from __future__ import annotations

import time
from copy import deepcopy

from . import observer
from .evaluator import evaluate_step
from .repair import build_repair_step, strategy_for_failure
from .safety import guard_step
from .state import (
    append_run_history,
    get_run_context,
    increment_run_counter,
    is_run_cancelled,
    record_safety_event,
    update_run_context,
)
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


def _record_step_history(run_id: str, step, status: str, **extra):
    append_run_history(
        run_id,
        'step_history',
        {
            'step_id': step.id,
            'name': step.name,
            'tool': step.tool,
            'action': step.action_type,
            'status': status,
            'timestamp': time.time(),
            **extra,
        },
    )


def _record_failure(run_id: str, step, decision: dict, observation_map: dict):
    failure_item = {
        'step_id': step.id,
        'action': step.action_type,
        'failure_class': decision.get('failure_class'),
        'reason': decision.get('reason'),
        'signature': decision.get('signature'),
        'timestamp': time.time(),
        'detail': observation_map.get('failure_detail') or observation_map.get('last_error'),
    }
    append_run_history(run_id, 'failure_history', failure_item)
    update_run_context(run_id, {'last_failure_class': decision.get('failure_class')})


def _record_safety_history(run_id: str, event: dict):
    record_safety_event(event)
    append_run_history(run_id, 'safety_history', event)


def _apply_repair(run_id: str, step, decision: dict, result: dict, observation_map: dict, event_cb) -> tuple[dict, dict]:
    task_type = ((get_run_context(run_id) or {}).get('plan') or {}).get('signature')
    strategy = strategy_for_failure(decision.get('failure_class'), task_type=task_type)
    repair_step = build_repair_step(step, result, int(time.time() * 1000) % 1000, strategy)
    if not repair_step:
        return {}, observation_map
    _emit_step(event_cb, run_id, step, 'repairing', message=decision.get('reason'), repair_strategy=strategy.name)
    _record_step_history(run_id, step, 'repairing', repair_strategy=strategy.name, failure_class=decision.get('failure_class'))
    repair_result = dispatch_tool_action(type('RepairStep', (), repair_step)())
    repair_observation = observer.normalize_tool_observation(repair_result, observation_map)
    repair_record = {
        'step_id': step.id,
        'failure_class': decision.get('failure_class'),
        'strategy': strategy.name,
        'reason': decision.get('reason'),
        'change_summary': repair_result.get('result', {}).get('change_summary'),
        'diff': repair_result.get('result', {}).get('diff'),
        'before_hash': repair_result.get('result', {}).get('before_hash'),
        'after_hash': repair_result.get('result', {}).get('after_hash'),
        'timestamp': time.time(),
        'ok': repair_result.get('ok', False),
    }
    append_run_history(run_id, 'repair_history', repair_record)
    update_run_context(run_id, {'last_repair': repair_record, 'last_observation': repair_observation})
    increment_run_counter(run_id, 'total_repairs', 1)
    repair_attempts = dict((get_run_context(run_id) or {}).get('repair_attempts', {}))
    repair_attempts[step.id] = repair_attempts.get(step.id, 0) + 1
    update_run_context(run_id, {'repair_attempts': repair_attempts})
    return repair_result, repair_observation


def execute_steps(run_id: str, steps, event_cb, wait_poll_ms: int = 100, start_index: int = 0):
    out = []
    for idx, step in enumerate(steps[start_index:], start=start_index):
        if is_run_cancelled(run_id):
            event_cb({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
            update_run_context(run_id, {'terminal_outcome': 'cancelled', 'status': 'cancelled'})
            return out + [{'step': step.id, 'status': 'cancelled', 'step_index': idx}]

        ctx = get_run_context(run_id) or {}
        last_obs = ctx.get('last_observation', {})
        if not _check_conditions(step, last_obs, 'pre'):
            out.append({'step': step.id, 'status': 'failed_precondition', 'step_index': idx})
            _record_step_history(run_id, step, 'failed_precondition')
            _emit_step(event_cb, run_id, step, 'fail', message='precondition failed', url=last_obs.get('url', ''))
            continue

        task_type = ((ctx.get('plan') or {}).get('signature')) if ctx else None
        guard = guard_step(step, task_type=task_type)
        if guard == 'blocked':
            out.append({'step': step.id, 'status': 'blocked', 'step_index': idx})
            event = {'kind': 'blocked', 'run_id': run_id, 'step_id': step.id, 'action': step.action_type}
            _record_safety_history(run_id, event)
            _record_step_history(run_id, step, 'blocked')
            update_run_context(run_id, {'terminal_outcome': 'blocked', 'status': 'blocked'})
            _emit_step(event_cb, run_id, step, 'failed', message='blocked by safety', url=last_obs.get('url', ''))
            continue
        if guard == 'confirm':
            out.append({'step': step.id, 'status': 'needs_confirmation', 'step_index': idx})
            event = {'kind': 'confirmation', 'run_id': run_id, 'step_id': step.id, 'action': step.action_type}
            _record_safety_history(run_id, event)
            _record_step_history(run_id, step, 'needs_confirmation')
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
                update_run_context(run_id, {'terminal_outcome': 'cancelled', 'status': 'cancelled'})
                return out + [{'step': step.id, 'status': 'cancelled', 'step_index': idx}]

            _emit_step(event_cb, run_id, step, 'running', attempt=attempts + 1)
            step_to_run = deepcopy(step)
            if step_to_run.action_type == 'WAIT_FOR':
                target_ms = int(step_to_run.args.get('ms', 1000))
                elapsed = 0
                while elapsed < target_ms:
                    if is_run_cancelled(run_id):
                        event_cb({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
                        update_run_context(run_id, {'terminal_outcome': 'cancelled', 'status': 'cancelled'})
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
            _record_step_history(run_id, step, 'executed', attempt=attempts + 1)
            update_run_context(run_id, {'last_observation': observation_map, 'current_step_index': idx})

            if step.action_type in ('OS_PASTE', 'OS_WRITE_CLIPBOARD', 'OS_COPY_SELECTION'):
                _record_safety_history(run_id, {'kind': 'clipboard', 'run_id': run_id, 'step_id': step.id, 'action': step.action_type, 'ok': result.get('ok', False)})
            if step.action_type == 'WEB_UPLOAD':
                _record_safety_history(run_id, {'kind': 'upload', 'run_id': run_id, 'step_id': step.id, 'action': step.action_type, 'ok': result.get('ok', False), 'file_path': step.args.get('file_path')})

            decision = evaluate_step(step, result, observation_map, get_run_context(run_id) or {})
            if decision['success'] and _check_conditions(step, observation_map, 'post'):
                final_result = result
                final_status = 'success'
                _record_step_history(run_id, step, 'success')
                update_run_context(run_id, {'terminal_outcome': 'success'})
                break

            _record_failure(run_id, step, decision, observation_map)

            if decision['outcome'] == 'needs_user':
                _record_step_history(run_id, step, 'needs_user', failure_class=decision.get('failure_class'))
                update_run_context(run_id, {'paused': True, 'paused_step_index': idx, 'last_observation': observation_map, 'user_intervention_required': True, 'terminal_outcome': 'needs_user'})
                event_cb({'type': 'needs_user', 'run_id': run_id, 'status': 'needs_user', 'step_id': step.id, 'step_index': idx, 'message': decision.get('reason') or result.get('error') or 'User action required', 'url': observation_map.get('url', ''), 'session': 'login_required', 'failure_class': decision.get('failure_class')})
                return out + [{'step': step.id, 'status': 'needs_user', 'result': result, 'step_index': idx}]

            if decision['outcome'] == 'repair':
                repair_result, repair_observation = _apply_repair(run_id, step, decision, result, observation_map, event_cb)
                if repair_result.get('ok'):
                    from .memory import latest_execution_memory, remember_execution

                    previous = latest_execution_memory(f"script:{step.args.get('path', '')}:{decision['failure_class']}", 'repair_success')
                    reason = 'previously_successful_strategy' if previous else decision['reason']
                    remember_execution(
                        f"script:{step.args.get('path', '')}:{decision['failure_class']}",
                        'repair_success',
                        reason,
                        tags=['code', 'repair'],
                        metadata={'strategy': decision['strategy'], 'change_summary': repair_result.get('result', {}).get('change_summary')},
                    )
                    _emit_step(event_cb, run_id, step, 'repair_applied', repair_strategy=decision['strategy'], message=repair_result.get('result', {}).get('change_summary', 'repair applied'))
                    attempts += 1
                    last_obs = repair_observation
                    time.sleep(step.retry_policy.backoff_ms / 1000)
                    continue

                from .memory import remember_execution

                remember_execution(
                    f"script:{step.args.get('path', '')}:{decision['failure_class']}",
                    'repair_failed',
                    repair_result.get('error', 'repair_failed'),
                    tags=['code', 'repair'],
                    metadata={'strategy': decision['strategy']},
                )
                _record_step_history(run_id, step, 'repair_failed', failure_class=decision.get('failure_class'), repair_strategy=decision.get('strategy'))
                final_result = repair_result
                final_status = 'terminal_failure'
                update_run_context(run_id, {'terminal_outcome': 'failed'})
                _emit_step(event_cb, run_id, step, 'terminal_failure', failure_class=decision.get('failure_class'), repair_strategy=decision.get('strategy'), message=repair_result.get('error', 'repair failed'))
                break

            if decision['outcome'] == 'retry':
                attempts += 1
                last_obs = observation_map
                _record_step_history(run_id, step, 'retrying', failure_class=decision.get('failure_class'))
                _emit_step(event_cb, run_id, step, 'retrying', failure_class=decision.get('failure_class'), message=decision.get('reason'))
                time.sleep(step.retry_policy.backoff_ms / 1000)
                continue

            final_result = result
            final_status = 'terminal_failure' if decision.get('terminal') else 'fail'
            _record_step_history(run_id, step, final_status, failure_class=decision.get('failure_class'), repair_strategy=decision.get('strategy'))
            update_run_context(run_id, {'terminal_outcome': 'failed'})
            _emit_step(event_cb, run_id, step, final_status, failure_class=decision.get('failure_class'), repair_strategy=decision.get('strategy'), message=decision.get('reason'))
            break

        final_observation = observer.normalize_tool_observation(final_result or {}, last_obs)
        out.append({'step': step.id, 'status': final_status, 'result': final_result, 'step_index': idx})
        if final_status == 'success':
            _emit_step(
                event_cb,
                run_id,
                step,
                final_status,
                message='',
                url=final_observation.get('url', ''),
                session='active' if not final_observation.get('login_required') else 'login_required',
            )
        if final_status in {'terminal_failure', 'fail'}:
            update_run_context(run_id, {'last_failure_class': final_observation.get('failure_class'), 'terminal_outcome': 'failed'})

    event_cb({'type': 'run_done', 'run_id': run_id, 'status': 'done', 'timestamp': time.time(), 'run_state': get_run_context(run_id)})
    return out
