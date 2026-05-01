from __future__ import annotations

from aura.user_tools import build_user_ai_prompt
from tools.tool_result import failure, success


def handle_user_ai_action(step, run_context: dict | None = None) -> dict:
    if step.action_type != 'USER_AI_PREPARE_PROMPT':
        return failure(step.action_type, error='unsupported_user_ai_action')
    args = step.args or {}
    prepared = build_user_ai_prompt(
        task=args.get('task') or (run_context or {}).get('text') or step.name,
        tool_id=args.get('tool_id') or 'chatgpt',
        context=args.get('context') or (run_context or {}).get('planning_context') or {},
        mode=args.get('mode') or 'general',
    )
    return success(
        'USER_AI_PREPARE_PROMPT',
        result=prepared,
        observation={
            'tool_id': prepared['tool']['tool_id'],
            'provider': prepared['tool']['provider'],
            'prompt_length': prepared['prompt_length'],
            'prompt_ready': True,
        },
    )
