from __future__ import annotations

from typing import Any

from .repair import strategy_for_failure

MAX_TOTAL_REPAIRS_PER_RUN = 6
MAX_IDENTICAL_FAILURES = 2



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



def _failure_signature(step, result: dict, observation_map: dict) -> str:
    return '|'.join([
        step.action_type,
        observation_map.get('failure_class') or 'unknown_error',
        str(result.get('error') or ''),
        str(observation_map.get('failure_detail') or ''),
    ])



def evaluate_step(step, result: dict[str, Any], observation_map: dict[str, Any], run_context: dict[str, Any]) -> dict[str, Any]:
    if result.get('requires_user'):
        return {
            'outcome': 'needs_user',
            'success': False,
            'failure_class': observation_map.get('failure_class'),
            'retryable': False,
            'terminal': False,
            'strategy': None,
            'reason': result.get('error') or 'user_action_required',
        }

    if result.get('ok') and _expected_outcome_met(step, result, observation_map):
        return {
            'outcome': 'success',
            'success': True,
            'failure_class': None,
            'retryable': False,
            'terminal': False,
            'strategy': None,
            'reason': 'expected_outcome_met',
        }

    failure_class = observation_map.get('failure_class') or 'unknown_error'
    strategy = strategy_for_failure(failure_class)
    failure_signature = _failure_signature(step, result, observation_map)
    failure_history = run_context.get('failure_history', [])
    identical_failures = sum(1 for item in failure_history if item.get('signature') == failure_signature)
    repair_attempts = (run_context.get('repair_attempts', {}) or {}).get(step.id, 0)
    total_repairs = int(run_context.get('total_repairs', 0))

    if total_repairs >= MAX_TOTAL_REPAIRS_PER_RUN:
        return {
            'outcome': 'stop',
            'success': False,
            'failure_class': failure_class,
            'retryable': False,
            'terminal': True,
            'strategy': strategy.name,
            'reason': 'max_total_repairs_exceeded',
            'signature': failure_signature,
        }

    if identical_failures >= MAX_IDENTICAL_FAILURES:
        return {
            'outcome': 'stop',
            'success': False,
            'failure_class': failure_class,
            'retryable': False,
            'terminal': True,
            'strategy': strategy.name,
            'reason': 'identical_failure_repeated',
            'signature': failure_signature,
        }

    if strategy.escalate_to_user:
        return {
            'outcome': 'needs_user',
            'success': False,
            'failure_class': failure_class,
            'retryable': False,
            'terminal': False,
            'strategy': strategy.name,
            'reason': strategy.stop_reason or 'manual_intervention_required',
            'signature': failure_signature,
        }

    if strategy.auto_repair and repair_attempts < strategy.max_attempts:
        return {
            'outcome': 'repair',
            'success': False,
            'failure_class': failure_class,
            'retryable': True,
            'terminal': False,
            'strategy': strategy.name,
            'reason': f'auto_repair_for_{failure_class}',
            'signature': failure_signature,
        }

    if strategy.terminal or not result.get('retryable', False):
        return {
            'outcome': 'stop',
            'success': False,
            'failure_class': failure_class,
            'retryable': False,
            'terminal': True,
            'strategy': strategy.name,
            'reason': strategy.stop_reason or 'unrecoverable_failure',
            'signature': failure_signature,
        }

    return {
        'outcome': 'retry',
        'success': False,
        'failure_class': failure_class,
        'retryable': True,
        'terminal': False,
        'strategy': strategy.name,
        'reason': 'retryable_failure',
        'signature': failure_signature,
    }
