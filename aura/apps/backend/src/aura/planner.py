from __future__ import annotations
import re
from .steps import Step
from .prefs import should_ask, get_pref_value


def intent_signature(text: str) -> str:
    t = text.lower()
    if t.startswith('search '):
        return 'search:web'
    if 'gmail' in t:
        return 'gmail:web'
    if t.startswith('find flights from'):
        return 'flights:web'
    return 'generic:noop'


def _gmail_clarifications() -> list[dict]:
    asks = []
    for key, options in {
        'gmail.browser': ['Default', 'Chrome', 'Safari'],
        'gmail.mode': ['Web', 'App'],
        'gmail.account': ['Primary', 'Other'],
    }.items():
        if should_ask(key):
            asks.append({'key': key, 'options': options})
    return asks


def plan_from_text(text: str, choices: dict | None = None) -> dict:
    choices = choices or {}
    t = text.lower().strip()
    clarifications = []
    if t.startswith('open gmail'):
        clarifications = _gmail_clarifications()
        if clarifications:
            return {'clarifications': clarifications, 'steps': [], 'signature': intent_signature(text)}
        browser = get_pref_value('gmail.browser') or 'Default'
        mode = get_pref_value('gmail.mode') or 'Web'
        url = 'https://mail.google.com'
        if mode == 'App':
            return {'clarifications': [], 'steps': [Step(id='s1', name='Gmail app not yet supported', action_type='NOOP', args={'message': 'Use web mode'})], 'signature': intent_signature(text)}
        return {'clarifications': [], 'steps': [Step(id='s1', name=f'Open Gmail in {browser}', action_type='WEB_NAVIGATE', args={'url': url})], 'signature': intent_signature(text)}

    if t.startswith('summarize unread emails'):
        return {'clarifications': [], 'steps': [Step(id='s1', name='Read Gmail unread', action_type='WEB_READ', args={'target': 'gmail_unread'})], 'signature': intent_signature(text)}

    if t.startswith('search '):
        q = re.sub(r'\s+and give me key points$', '', text[7:], flags=re.I)
        return {'clarifications': [], 'steps': [Step(id='s1', name='Search web', action_type='WEB_READ', args={'target': 'search', 'query': q})], 'signature': intent_signature(text), 'slots': {'query': q}}

    if t.startswith('find flights from'):
        m = re.search(r'find flights from\s+(\S+)\s+to\s+(\S+)\s+on\s+([^\s]+)\s+return\s+([^\s]+)', t)
        args = {'target': 'flights', 'query': text}
        slots = {}
        if m:
            slots = {'origin': m.group(1).upper(), 'dest': m.group(2).upper(), 'depart': m.group(3), 'return': m.group(4)}
            args.update(slots)
        return {'clarifications': [], 'steps': [Step(id='s1', name='Search flights', action_type='WEB_READ', args=args)], 'signature': intent_signature(text), 'slots': slots}

    return {'clarifications': [], 'steps': [Step(id='s1', name='Noop', action_type='NOOP', args={'echo': text})], 'signature': intent_signature(text)}
