from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class UserWebTool:
    tool_id: str
    label: str
    provider: str
    url: str
    description: str
    owned_by: str = 'user'
    safety_notes: tuple[str, ...] = ('User subscription/session is used through browser automation.', 'AURA does not send or submit final user content without approval.')

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data['safety_notes'] = list(self.safety_notes)
        return data


_TOOLS = {
    'chatgpt': UserWebTool('chatgpt', 'ChatGPT', 'openai', 'https://chatgpt.com/', 'Use the user-owned ChatGPT web session.'),
    'claude': UserWebTool('claude', 'Claude', 'anthropic', 'https://claude.ai/new', 'Use the user-owned Claude web session.'),
}


def list_user_web_tools() -> list[dict[str, Any]]:
    return [tool.to_dict() for tool in _TOOLS.values()]


def get_user_web_tool(tool_id: str) -> dict[str, Any] | None:
    tool = _TOOLS.get(tool_id)
    return tool.to_dict() if tool else None


def infer_user_tool(text: str) -> str:
    low = text.lower()
    if 'claude' in low:
        return 'claude'
    return 'chatgpt'


def build_user_ai_prompt(*, task: str, tool_id: str = 'chatgpt', context: dict[str, Any] | None = None, mode: str = 'general') -> dict[str, Any]:
    tool = get_user_web_tool(tool_id) or get_user_web_tool('chatgpt')
    ctx = context or {}
    source_text = ctx.get('input_text') or ctx.get('selected_text') or ctx.get('clipboard_text') or ''
    browser_url = ctx.get('browser_url') or ''
    workspace = ctx.get('workspace_hint') or ((ctx.get('project') or {}).get('current_folder')) or ''
    boundaries = [
        'Use only the context below.',
        'Do not assume private facts that are not provided.',
        'If this is an email/message, draft only; do not send.',
        'If this is code, produce a clear implementation prompt or patch plan.',
        'Keep secrets/API keys out of the response.',
    ]
    if mode == 'coding':
        boundaries.append('Return steps a coding agent can execute and tests it should run.')
    if mode == 'email':
        boundaries.append('Match the user tone and produce a paste-ready draft.')

    prompt = '\n'.join([
        'You are being used by AURA, the user-owned AI operating layer.',
        f'User task: {task}',
        f'Mode: {mode}',
        f'Current browser URL: {browser_url or "unknown"}',
        f'Workspace: {workspace or "unknown"}',
        'Rules:',
        *[f'- {rule}' for rule in boundaries],
        'Context:',
        source_text or '(No selected text was captured. Ask one concise clarification if needed.)',
        'Return:',
        '- The final answer/draft/prompt only.',
        '- No hidden actions.',
    ])
    return {
        'tool': tool,
        'prompt': prompt,
        'prompt_length': len(prompt),
        'mode': mode,
        'context_used': {
            'has_source_text': bool(source_text),
            'browser_url': browser_url,
            'workspace': workspace,
        },
    }
