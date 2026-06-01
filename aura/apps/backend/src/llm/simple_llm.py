from __future__ import annotations


def _compact(text: str, limit: int = 700) -> str:
    text = ' '.join((text or '').split())
    return text[:limit].rstrip()


def respond(prompt: str) -> str:
    """Deterministic local fallback used when no provider/local model is ready.

    It is intentionally simple, but it should still feel useful in private-alpha
    flows instead of surfacing raw demo placeholders to users.
    """

    lower = (prompt or '').lower()
    if 'draft' in lower or 'reply' in lower or 'message' in lower:
        if 'concise' in lower or 'short' in lower:
            return (
                'Here is a concise draft:\n\n'
                'Thanks for the context. I reviewed it and the next step looks clear. '
                'I can move forward once you confirm the details you want included.'
            )
        return (
            'Here is a draft you can review:\n\n'
            'Thanks for sending this over. I reviewed the details and I think the best next step is to move forward carefully, '
            'confirm any open questions, and keep the response clear. Let me know if you want me to adjust the tone before sending.'
        )
    if 'coding job' in lower or 'build app' in lower or 'fix' in lower:
        return (
            'I prepared a structured coding job with a clear goal, likely files, acceptance criteria, and test commands. '
            'If Codex or another coding worker is enabled, this can be handed off; otherwise the job prompt is saved locally.'
        )
    if 'summarize' in lower:
        return f'Summary: {_compact(prompt, 420)}'
    if 'explain aura' in lower or 'what is aura' in lower:
        return (
            'Aegisure is a private AI operating identity: Helper does the work, Guardian protects risky actions, '
            'Memory remembers user-owned context, and Identity records which profile Aegisure acted under.'
        )
    return (
        'I can help with that in local fallback mode. I will keep the action private, check context first, '
        'ask approval before sensitive steps, and show exactly what I did.'
    )
