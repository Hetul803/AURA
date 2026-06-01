from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from .privacy import detect_secret, detect_sensitive, redact_text, sensitivity_labels


@dataclass(frozen=True)
class UserWebTool:
    tool_id: str
    label: str
    provider: str
    url: str
    description: str
    owned_by: str = 'user'
    safety_notes: tuple[str, ...] = ('User subscription/session is used through browser automation.', 'Aegisure does not send or submit final user content without approval.')

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data['safety_notes'] = list(self.safety_notes)
        return data


_TOOLS = {
    'chatgpt': UserWebTool('chatgpt', 'ChatGPT', 'openai', 'https://chatgpt.com/', 'Use the user-owned ChatGPT web session.'),
    'claude': UserWebTool('claude', 'Claude', 'anthropic', 'https://claude.ai/new', 'Use the user-owned Claude web session.'),
    'codex': UserWebTool('codex', 'Codex', 'openai', 'https://chatgpt.com/codex', 'Prepare a safe coding handoff for Codex or Codex CLI.', safety_notes=('Aegisure prepares coding prompts and job files.', 'External execution requires explicit approval.')),
    'cursor': UserWebTool('cursor', 'Cursor', 'cursor', 'cursor://', 'Prepare a safe coding handoff for Cursor.', safety_notes=('Aegisure can prepare prompts for Cursor.', 'Pasting into Cursor requires approval.')),
}

EMAIL_RE = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
PHONE_RE = re.compile(r'(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)')


def _mask_contact(text: str) -> str:
    text = EMAIL_RE.sub('[REDACTED_EMAIL]', text)
    return PHONE_RE.sub('[REDACTED_PHONE]', text)


def privacy_check_for_handoff(*, prompt: str, destination: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = context or {}
    context_text = str(ctx)
    inspection_text = f'{prompt}\n{context_text}'
    labels = set(sensitivity_labels(inspection_text))
    if EMAIL_RE.search(inspection_text):
        labels.add('email_address')
    if PHONE_RE.search(inspection_text):
        labels.add('phone_number')
    if detect_sensitive(context_text):
        labels.add('sensitive_context')
    redacted = _mask_contact(redact_text(prompt, limit=12000))
    context_redacted = _mask_contact(redact_text(context_text, limit=12000))
    secret_detected = detect_secret(inspection_text) or '[REDACTED]' in redacted or '[REDACTED]' in context_redacted
    requires_approval = bool(labels)
    return {
        'destination': destination,
        'labels': sorted(labels),
        'secret_detected': secret_detected,
        'redacted': redacted != prompt or context_redacted != context_text,
        'requires_approval': requires_approval,
        'approval_reason': 'External AI handoff contains sensitive or identifying data.' if requires_approval else 'No sensitive data detected in the prepared handoff prompt.',
        'data_destination': destination,
        'safe_prompt': redacted,
        'summary': {
            'prompt_chars': len(prompt),
            'safe_prompt_chars': len(redacted),
            'context_fields': sorted(ctx.keys())[:20],
        },
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
    if 'codex' in low:
        return 'codex'
    if 'cursor' in low:
        return 'cursor'
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
        'You are being used by Aegisure, the user-owned AI operating layer.',
        f'User task: {task}',
        f'Mode: {mode}',
        f'Current browser URL: {browser_url or "unknown"}',
        f'Workspace: {workspace or "unknown"}',
        'Rules:',
        *[f'- {rule}' for rule in boundaries],
        'Context:',
        _mask_contact(redact_text(source_text)) or '(No selected text was captured. Ask one concise clarification if needed.)',
        'Return:',
        '- The final answer/draft/prompt only.',
        '- No hidden actions.',
    ])
    privacy_check = privacy_check_for_handoff(prompt=prompt, destination=tool['label'], context=ctx)
    safe_prompt = privacy_check['safe_prompt']
    return {
        'tool': tool,
        'prompt': safe_prompt,
        'raw_prompt_was_redacted': safe_prompt != prompt,
        'prompt_length': len(safe_prompt),
        'mode': mode,
        'privacy_check': privacy_check,
        'context_used': {
            'has_source_text': bool(source_text),
            'browser_url': browser_url,
            'workspace': workspace,
        },
    }
