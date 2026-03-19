from __future__ import annotations

from urllib.parse import urlparse

from .learning import query_relevant_memory

SENSITIVE = ['send', 'delete', 'pay', 'purchase', 'checkout']


def requires_confirmation(step_name: str) -> bool:
    low = step_name.lower()
    return any(s in low for s in SENSITIVE)


def guard_step(step, task_type: str | None = None) -> str:
    if step.safety_level == 'BLOCKED':
        return 'blocked'

    url = (step.args or {}).get('url')
    domain = urlparse(url).netloc if url else None
    safety_hints = query_relevant_memory(task_type=task_type, domain=domain, action_key=step.action_type)
    learned_confirm = any(item.get('policy') == 'require_confirmation' for item in safety_hints['safety'])
    learned_block = any(item.get('policy') == 'blocked' for item in safety_hints['safety'])

    if learned_block:
        return 'blocked'
    if step.safety_level == 'CONFIRM' or requires_confirmation(step.name) or learned_confirm:
        return 'confirm'
    return 'allow'
