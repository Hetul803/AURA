from __future__ import annotations

import time
from copy import deepcopy

from . import observer
from .evaluator import evaluate_step
from .guardian import record_step_events
from .repair import build_repair_step, strategy_for_failure
from .safety import step_risk
from .state import (
    append_run_history,
    create_approval_request,
    get_run_context,
    increment_run_counter,
    is_step_approved,
    is_run_cancelled,
    record_run_event,
    record_safety_event,
    update_run_context,
)
from tools.os_automation import read_clipboard
from tools.tool_router import dispatch_tool_action


ASSIST_CAPTURE = 'ASSIST_CAPTURE_CONTEXT'
ASSIST_RESEARCH = 'ASSIST_RESEARCH_CONTEXT'
ASSIST_DRAFT = 'ASSIST_DRAFT'
ASSIST_APPROVAL = 'ASSIST_WAIT_APPROVAL'
ASSIST_PASTE = 'ASSIST_PASTE_BACK'


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
    record_run_event(payload)
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
    repair_result = dispatch_tool_action(type('RepairStep', (), repair_step)(), get_run_context(run_id) or {})
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


def _update_assist_context(run_id: str, step, result: dict):
    current = get_run_context(run_id) or {}
    payload: dict = {}
    assist_state = {**(current.get('assist') or {})}
    if step.action_type == ASSIST_CAPTURE:
        captured = result.get('result', {}).get('captured_context') or {}
        payload['captured_context'] = captured
        intent = {**(assist_state.get('intent') or {})}
        intent['source_text_present'] = bool(captured.get('input_text'))
        assist_state.update({
            'captured_context': captured,
            'intent': intent,
            'capture_path': captured.get('capture_path_used') or captured.get('input_source'),
            'capture': {
                'capture_path_used': captured.get('capture_path_used') or captured.get('input_source'),
                'clipboard_preserved': ((captured.get('capture_method') or {}).get('clipboard_preserved')),
                'clipboard_restored_after_capture': ((captured.get('capture_method') or {}).get('clipboard_restored_after_capture')),
                'capture_failure_reason': ((captured.get('capture_method') or {}).get('capture_failure_reason')),
            },
            'target_fingerprint': captured.get('target_fingerprint') or captured.get('paste_target') or {},
        })
        payload['assist'] = assist_state
    elif step.action_type == ASSIST_RESEARCH:
        research = result.get('result', {}).get('research_context') or {}
        payload['research_context'] = research
        assist_state.update({'research_context': research, 'research_used': bool(research.get('search_used') or research.get('page_context'))})
        payload['assist'] = assist_state
    elif step.action_type == ASSIST_DRAFT:
        draft = result.get('result', {}).get('draft') or {}
        approval_state = {
            'required': True,
            'status': 'pending',
            'draft_text': draft.get('draft_text', ''),
            'edited_text': '',
            'final_text': '',
            'feedback': draft.get('feedback', ''),
            'requested_at': time.time(),
            'approved_by_user': False,
            'paste_after_approval': True,
            'generated_text': draft.get('draft_text', ''),
        }
        payload['draft_state'] = draft
        payload['approval_state'] = approval_state
        assist_state.update({
            'draft': draft,
            'generation': {
                'provider': draft.get('provider'),
                'model': draft.get('model'),
                'fallback_used': draft.get('fallback_used', False),
                'confidence': draft.get('confidence'),
                'notes': draft.get('notes', []),
            },
            'style_signals_used': draft.get('style_hints', {}),
            'learning_signals': draft.get('learning_signals_applied', {}),
        })
        payload['assist'] = assist_state
    elif step.action_type == ASSIST_PASTE:
        observation = result.get('observation') or {}
        paste_state = {
            'status': 'pasted' if result.get('ok') else 'failed',
            'pasted_length': result.get('result', {}).get('pasted', result.get('pasted', 0)),
            'target_validation': observation.get('target_validation'),
            'target_validation_result': observation.get('target_validation_result'),
            'strict_validation': observation.get('strict_validation', False),
            'cautious_validation': observation.get('cautious_validation', False),
            'clipboard_preserved': observation.get('clipboard_preserved'),
            'clipboard_restored_after_paste': observation.get('clipboard_restored_after_paste'),
            'clipboard_restore_error_after_paste': observation.get('clipboard_restore_error_after_paste'),
            'paste_attempted': observation.get('paste_attempted', False),
            'paste_blocked_reason': observation.get('paste_blocked_reason'),
            'context_drift_reason': observation.get('context_drift_reason'),
            'target_fingerprint': observation.get('target_fingerprint') or (current.get('captured_context') or {}).get('target_fingerprint') or {},
        }
        payload['pasteback_state'] = paste_state
        approval_state = {**(current.get('approval_state') or {})}
        approval_state['status'] = 'pasted' if result.get('ok') else approval_state.get('status', 'approved')
        payload['approval_state'] = approval_state
        assist_state['paste_validation'] = paste_state
        assist_state['final_outcome'] = 'pasted' if result.get('ok') else 'paste_blocked'
        payload['assist'] = assist_state
    if payload:
        update_run_context(run_id, payload)


def execute_steps(run_id: str, steps, event_cb, wait_poll_ms: int = 100, start_index: int = 0):
    out = []
    for idx, step in enumerate(steps[start_index:], start=start_index):
        if is_run_cancelled(run_id):
            record_run_event({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
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
        risk_decision = step_risk(step, task_type=task_type)
        guard = risk_decision['decision']
        if guard == 'blocked':
            out.append({'step': step.id, 'status': 'blocked', 'step_index': idx})
            event = {
                'kind': 'blocked',
                'run_id': run_id,
                'step_id': step.id,
                'action': step.action_type,
                'risk_level': risk_decision.get('risk'),
                'message': risk_decision.get('reason') or 'blocked by safety',
            }
            _record_safety_history(run_id, event)
            _record_step_history(run_id, step, 'blocked')
            update_run_context(run_id, {'terminal_outcome': 'blocked', 'status': 'blocked'})
            _emit_step(event_cb, run_id, step, 'failed', message=f"AURA Guardian blocked this action: {event['message']}", url=last_obs.get('url', ''), guardian_reason=event['message'])
            return out
        if guard == 'confirm' and step.action_type not in (ASSIST_APPROVAL, ASSIST_PASTE) and not is_step_approved(run_id, step.id):
            approval = create_approval_request(run_id, step, risk_decision.get('reason') or 'confirmation_required')
            out.append({'step': step.id, 'status': 'awaiting_approval', 'step_index': idx, 'approval': approval})
            event = {'kind': 'confirmation', 'run_id': run_id, 'step_id': step.id, 'action': step.action_type, 'risk_level': risk_decision.get('risk') or step.safety_level, 'approval_id': approval['approval_id'], 'message': approval['risk_reason']}
            _record_safety_history(run_id, event)
            _record_step_history(run_id, step, 'needs_confirmation')
            update_run_context(run_id, {
                'paused': True,
                'paused_step_index': idx,
                'status': 'awaiting_approval',
                'terminal_outcome': 'needs_approval',
                'user_intervention_required': True,
                'approval_state': {
                    'kind': 'tool_confirmation',
                    'required': True,
                    'status': 'pending',
                    'approval_id': approval['approval_id'],
                    'step_id': step.id,
                    'step_name': step.name,
                    'action_type': step.action_type,
                    'tool': step.tool,
                    'risk_reason': approval['risk_reason'],
                    'risk_level': risk_decision.get('risk'),
                    'requested_args': step.args,
                },
            })
            payload = {
                'type': 'approval_required',
                'run_id': run_id,
                'status': 'awaiting_approval',
                'step_id': step.id,
                'step_index': idx,
                'approval_id': approval['approval_id'],
                'message': 'Confirmation required before AURA can continue.',
                'action_type': step.action_type,
                'risk_reason': approval['risk_reason'],
                'risk_level': risk_decision.get('risk'),
                'url': last_obs.get('url', ''),
            }
            record_run_event(payload)
            event_cb(payload)
            return out

        _emit_step(event_cb, run_id, step, 'planned')
        attempts = 0
        max_attempts = step.retry_policy.max_retries + 1
        final_result = None
        final_status = 'fail'

        while attempts < max_attempts:
            if is_run_cancelled(run_id):
                record_run_event({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
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
                        record_run_event({'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled'})
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
                if step_to_run.action_type == 'ASSIST_PASTE_BACK':
                    approval = (ctx.get('approval_state') or {})
                    step_to_run.args['text'] = approval.get('final_text') or approval.get('edited_text') or approval.get('draft_text') or ''
                result = dispatch_tool_action(step_to_run, get_run_context(run_id) or {})

            observation_map = observer.normalize_tool_observation(result, last_obs)
            _record_step_history(run_id, step, 'executed', attempt=attempts + 1)
            update_run_context(run_id, {'last_observation': observation_map, 'current_step_index': idx})
            _update_assist_context(run_id, step, result)
            guardian_events = record_step_events(run_id, step, result, get_run_context(run_id) or {})
            for guardian_event in guardian_events:
                event_cb({'type': 'guardian_event', 'run_id': run_id, 'status': 'running', **guardian_event})

            if step.action_type in ('OS_PASTE', 'OS_WRITE_CLIPBOARD', 'OS_COPY_SELECTION', ASSIST_PASTE):
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
                paused_patch = {'paused': True, 'paused_step_index': idx, 'last_observation': observation_map, 'user_intervention_required': True, 'terminal_outcome': 'needs_user'}
                event_type = 'needs_user'
                message = decision.get('reason') or result.get('error') or 'User action required'
                if step.action_type == ASSIST_APPROVAL:
                    approval_state = {**((get_run_context(run_id) or {}).get('approval_state') or {})}
                    approval_state['status'] = 'pending'
                    paused_patch.update({'paused_step_index': idx + 1, 'approval_state': approval_state, 'status': 'awaiting_approval', 'user_intervention_required': False})
                    event_type = 'approval_required'
                    message = 'Draft ready for approval.'
                update_run_context(run_id, paused_patch)
                payload = {'type': event_type, 'run_id': run_id, 'status': paused_patch.get('status', 'needs_user'), 'step_id': step.id, 'step_index': idx, 'message': message, 'url': observation_map.get('url', ''), 'session': 'login_required', 'failure_class': decision.get('failure_class')}
                record_run_event(payload)
                event_cb(payload)
                return out + [{'step': step.id, 'status': paused_patch.get('status', 'needs_user'), 'result': result, 'step_index': idx}]

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
                message='done' if step.action_type == ASSIST_PASTE else '',
                url=final_observation.get('url', ''),
                session='active' if not final_observation.get('login_required') else 'login_required',
            )
    return out
