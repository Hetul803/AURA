from __future__ import annotations

from aura.agent_router import route_agent
from tools.tool_result import failure, success


def handle_agent_action(step, run_context: dict | None = None) -> dict:
    if step.action_type != 'AGENT_DELEGATE':
        return failure(step.action_type, error='unsupported_agent_action')
    args = step.args or {}
    route = route_agent(
        task=args.get('task') or (run_context or {}).get('text') or step.name,
        task_type=args.get('task_type') or ((run_context or {}).get('plan') or {}).get('signature'),
        context=args.get('context') or (run_context or {}).get('planning_context') or ((run_context or {}).get('plan') or {}).get('context') or {},
        observation=args.get('observation') or (run_context or {}).get('last_observation'),
    )
    return success(
        'AGENT_DELEGATE',
        result={'route': route, 'agent_prompt': route['agent_prompt']},
        observation={
            'agent_id': route['agent_id'],
            'route_reason': route['reason'],
            'agent_status': route.get('status'),
            'task_type': route.get('task_type'),
        },
    )
