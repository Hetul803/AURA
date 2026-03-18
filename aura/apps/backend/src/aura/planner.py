from __future__ import annotations
import re
from .steps import Step, Condition
from .prefs import should_ask, get_pref_value


def intent_signature(text: str) -> str:
    t = text.lower()
    if t.startswith('search '): return 'search:web'
    if 'gmail' in t: return 'gmail:web'
    if t.startswith('find flights from'): return 'flights:web'
    if 'selected text' in t: return 'selection:web'
    if 'open cursor' in t: return 'cursor:os'
    if 'open this folder' in t or 'open this file' in t: return 'open_path:os'
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
    t = text.lower().strip()
    if t.startswith('open gmail, summarize unread emails, draft a reply'):
        steps = [
            Step(id='s1', name='Open Gmail', action_type='WEB_NAVIGATE', args={'url': 'https://mail.google.com'}, postconditions=[Condition(type='url_contains', key='url', expected='mail.google.com')]),
            Step(id='s2', name='Summarize unread emails', action_type='WEB_READ', args={'target': 'gmail_unread'}),
            Step(id='s3', name='Write draft reply to clipboard', action_type='OS_WRITE_CLIPBOARD', args={'text': 'Thanks for the update. I reviewed this and will follow up shortly.'}),
            Step(id='s4', name='Paste draft in active app (do not send)', action_type='OS_PASTE', args={'text': 'Thanks for the update. I reviewed this and will follow up shortly.'}, safety_level='CONFIRM'),
        ]
        return {'clarifications': [], 'steps': steps, 'signature': intent_signature(text)}

    if t.startswith('take the selected text, search it'):
        steps = [
            Step(id='s1', name='Copy selected text', action_type='OS_COPY_SELECTION'),
            Step(id='s2', name='Search selected text', action_type='WEB_READ', args={'target': 'search', 'query': '__FROM_CLIPBOARD__'}),
        ]
        return {'clarifications': [], 'steps': steps, 'signature': intent_signature(text)}

    if t.startswith('open cursor and paste this website prompt'):
        prompt = text.split(':',1)[1].strip() if ':' in text else 'Build a modern landing page with hero, features, and CTA.'
        steps = [
            Step(id='s1', name='Open Cursor', action_type='OS_OPEN_APP', args={'app_name': 'Cursor'}),
            Step(id='s2', name='Activate Cursor', action_type='OS_ACTIVATE_APP', args={'app_name': 'Cursor'}),
            Step(id='s3', name='Paste prompt', action_type='OS_PASTE', args={'text': prompt}, safety_level='CONFIRM'),
        ]
        return {'clarifications': [], 'steps': steps, 'signature': intent_signature(text), 'slots': {'prompt': prompt}}

    if t.startswith('open this folder') or t.startswith('open this file'):
        m = re.search(r'"([^"]+)"', text)
        p = m.group(1) if m else ''
        return {'clarifications': [], 'steps': [Step(id='s1', name='Open path', action_type='OS_OPEN_PATH', args={'path': p})], 'signature': intent_signature(text)}

    if t.startswith('open gmail'):
        clarifications = _gmail_clarifications()
        if clarifications:
            return {'clarifications': clarifications, 'steps': [], 'signature': intent_signature(text)}
        browser = get_pref_value('gmail.browser') or 'Default'
        mode = get_pref_value('gmail.mode') or 'Web'
        if mode == 'App':
            return {'clarifications': [], 'steps': [Step(id='s1', name='Gmail app not yet supported', action_type='NOOP', args={'message': 'Use web mode'})], 'signature': intent_signature(text)}
        return {'clarifications': [], 'steps': [Step(id='s1', name=f'Open Gmail in {browser}', action_type='WEB_NAVIGATE', args={'url': 'https://mail.google.com'})], 'signature': intent_signature(text)}

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
