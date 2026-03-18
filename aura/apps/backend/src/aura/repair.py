from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RepairStrategy:
    name: str
    failure_class: str
    auto_repair: bool
    max_attempts: int
    escalate_to_user: bool = False
    terminal: bool = False
    stop_reason: str | None = None


STRATEGIES: dict[str, RepairStrategy] = {
    'syntax_error': RepairStrategy('repair_python_syntax', 'syntax_error', auto_repair=True, max_attempts=2),
    'name_error': RepairStrategy('repair_python_name', 'name_error', auto_repair=True, max_attempts=2),
    'import_error': RepairStrategy('stop_import_error', 'import_error', auto_repair=False, max_attempts=0, terminal=True, stop_reason='import_error_requires_manual_fix'),
    'dependency_error': RepairStrategy('stop_dependency_error', 'dependency_error', auto_repair=False, max_attempts=0, escalate_to_user=True, stop_reason='dependency_install_required'),
    'file_not_found': RepairStrategy('stop_file_not_found', 'file_not_found', auto_repair=False, max_attempts=0, terminal=True, stop_reason='missing_file'),
    'permission_error': RepairStrategy('stop_permission_error', 'permission_error', auto_repair=False, max_attempts=0, escalate_to_user=True, stop_reason='permission_required'),
    'runtime_error': RepairStrategy('stop_runtime_error', 'runtime_error', auto_repair=False, max_attempts=0, terminal=True, stop_reason='runtime_error_unrecoverable'),
    'unknown_error': RepairStrategy('stop_unknown_error', 'unknown_error', auto_repair=False, max_attempts=0, terminal=True, stop_reason='unknown_failure'),
}



def strategy_for_failure(failure_class: str | None) -> RepairStrategy:
    return STRATEGIES.get(failure_class or 'unknown_error', STRATEGIES['unknown_error'])



def build_repair_step(step, result: dict[str, Any], attempt: int, strategy: RepairStrategy) -> dict | None:
    if not strategy.auto_repair:
        return None
    if step.action_type != 'CODE_RUN':
        return None
    observation = result.get('observation') or {}
    return {
        'id': f'{step.id}:repair:{attempt}',
        'name': f'Repair {step.name}',
        'action_type': 'CODE_REPAIR',
        'tool': 'code',
        'args': {
            'path': step.args.get('path', ''),
            'error': result.get('error'),
            'observation': observation,
            'failure_class': observation.get('failure_class'),
            'strategy': strategy.name,
        },
    }
