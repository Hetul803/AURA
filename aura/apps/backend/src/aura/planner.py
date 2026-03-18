from __future__ import annotations

import re
from pathlib import Path

from .memory import execution_hints, latest_memory
from .prefs import should_ask, get_pref_value
from .steps import Step, Condition, RetryPolicy



def intent_signature(text: str) -> str:
    t = text.lower().strip()
    if t.startswith('fix and run python script at') or t.startswith('run python script at'):
        return 'code:python_script'
    if t.startswith('search '):
        return 'search:web'
    if 'gmail' in t:
        return 'gmail:web'
    if t.startswith('find flights from'):
        return 'flights:web'
    if 'selected text' in t:
        return 'selection:web'
    if 'open cursor' in t:
        return 'cursor:os'
    if 'open this folder' in t or 'open this file' in t:
        return 'open_path:os'
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



def _build_plan(*, goal: str, signature: str, steps: list[Step], context: dict | None = None,
                success_criteria: list[dict] | None = None, clarifications: list[dict] | None = None,
                memory_scope: str | None = None, slots: dict | None = None) -> dict:
    scope = memory_scope or signature
    return {
        'goal': goal,
        'signature': signature,
        'context': context or {},
        'steps': steps,
        'success_criteria': success_criteria or [],
        'clarifications': clarifications or [],
        'memory_hints': execution_hints(scope),
        'slots': slots or {},
    }



def _extract_quoted_path(text: str) -> str:
    match = re.search(r'"([^"]+)"', text)
    if match:
        return match.group(1)
    match = re.search(r"'([^']+)'", text)
    if match:
        return match.group(1)
    return text.rsplit(' ', 1)[-1]



def _code_plan(text: str) -> dict:
    path = _extract_quoted_path(text)
    signature = intent_signature(text)
    last_success = latest_memory(f'exec:script:{path}:success')
    workspace = str(Path(path).expanduser().parent) if path else ''
    steps = [
        Step(
            id='s1',
            name='Validate script path',
            action_type='FS_EXISTS',
            tool='filesystem',
            args={'path': path},
            expected_outcome={'exists': True},
            postconditions=[Condition(type='bool', key='file_exists', expected=True)],
            fallback_hint='ask_for_correct_path',
        ),
        Step(
            id='s2',
            name='Run python script',
            action_type='CODE_RUN',
            tool='code',
            args={'path': path, 'workspace': workspace, 'kind': 'python'},
            expected_outcome={'exit_code': 0},
            fallback_hint='repair_python_and_retry',
            retry_policy=RetryPolicy(max_retries=2, backoff_ms=50),
        ),
    ]
    context = {'script_path': path, 'workspace': workspace, 'last_success_hint': last_success['value'] if last_success else None}
    success_criteria = [{'type': 'exit_code', 'expected': 0}, {'type': 'artifact_exists', 'expected': path}]
    return _build_plan(
        goal=f'Execute and, if needed, repair the Python script at {path}',
        signature=signature,
        steps=steps,
        context=context,
        success_criteria=success_criteria,
        memory_scope=f'script:{path}',
    )



def plan_from_text(text: str, choices: dict | None = None) -> dict:
    t = text.lower().strip()

    if t.startswith('fix and run python script at') or t.startswith('run python script at'):
        return _code_plan(text)

    if t.startswith('open gmail, summarize unread emails, draft a reply'):
        return _build_plan(
            goal='Open Gmail, summarize unread emails, draft a reply, and paste it into the current reply box without sending',
            signature=intent_signature(text),
            steps=[
                Step(id='s1', name='Open Gmail', action_type='WEB_NAVIGATE', tool='browser', args={'url': 'https://mail.google.com'}, expected_outcome={'url_contains': 'mail.google.com'}),
                Step(id='s2', name='Summarize unread emails', action_type='WEB_READ', tool='browser', args={'target': 'gmail_unread'}, expected_outcome={'unread_count_gte': 0}),
                Step(id='s3', name='Write draft reply to clipboard', action_type='OS_WRITE_CLIPBOARD', tool='os', args={'text': 'Thanks for the update. I reviewed this and will follow up shortly.'}, expected_outcome={'written_gte': 10}),
                Step(id='s4', name='Paste draft in active app (do not send)', action_type='OS_PASTE', tool='os', args={'text': 'Thanks for the update. I reviewed this and will follow up shortly.'}, expected_outcome={'pasted_gte': 10}, safety_level='CONFIRM'),
            ],
            success_criteria=[{'type': 'gmail_summary_ready'}, {'type': 'draft_pasted'}],
        )

    if t.startswith('take the selected text, search it'):
        return _build_plan(
            goal='Capture selected text, research it on the web, and return key points',
            signature=intent_signature(text),
            steps=[
                Step(id='s1', name='Copy selected text', action_type='OS_COPY_SELECTION', tool='os', expected_outcome={'clipboard_length_gte': 1}),
                Step(id='s2', name='Search selected text', action_type='WEB_READ', tool='browser', args={'target': 'search', 'query': '__FROM_CLIPBOARD__'}, expected_outcome={'key_points_gte': 1}),
            ],
            success_criteria=[{'type': 'key_points_gte', 'expected': 1}],
        )

    if t.startswith('open cursor and paste this website prompt'):
        prompt = text.split(':', 1)[1].strip() if ':' in text else 'Build a modern landing page with hero, features, and CTA.'
        return _build_plan(
            goal='Open Cursor and paste a provided website prompt into the active editor',
            signature=intent_signature(text),
            steps=[
                Step(id='s1', name='Open Cursor', action_type='OS_OPEN_APP', tool='os', args={'app_name': 'Cursor'}, expected_outcome={'active_app_contains': 'Cursor'}),
                Step(id='s2', name='Activate Cursor', action_type='OS_ACTIVATE_APP', tool='os', args={'app_name': 'Cursor'}, expected_outcome={'active_app_contains': 'Cursor'}),
                Step(id='s3', name='Paste prompt', action_type='OS_PASTE', tool='os', args={'text': prompt}, expected_outcome={'pasted_gte': len(prompt) // 2}, safety_level='CONFIRM'),
            ],
            context={'prompt': prompt},
            success_criteria=[{'type': 'prompt_pasted'}],
            slots={'prompt': prompt},
        )

    if t.startswith('open this folder') or t.startswith('open this file'):
        path = _extract_quoted_path(text)
        return _build_plan(
            goal=f'Open the requested path {path}',
            signature=intent_signature(text),
            steps=[Step(id='s1', name='Open path', action_type='OS_OPEN_PATH', tool='os', args={'path': path}, expected_outcome={'opened_path': path})],
            context={'path': path},
            success_criteria=[{'type': 'path_opened', 'expected': path}],
        )

    if t.startswith('open gmail'):
        clarifications = _gmail_clarifications()
        if clarifications:
            return _build_plan(goal='Open Gmail with the user preferred settings', signature=intent_signature(text), steps=[], clarifications=clarifications)
        browser = get_pref_value('gmail.browser') or 'Default'
        mode = get_pref_value('gmail.mode') or 'Web'
        if mode == 'App':
            return _build_plan(goal='Open Gmail app mode', signature=intent_signature(text), steps=[Step(id='s1', name='Gmail app not yet supported', action_type='NOOP', tool='control', args={'message': 'Use web mode'})])
        return _build_plan(goal='Open Gmail in browser', signature=intent_signature(text), steps=[Step(id='s1', name=f'Open Gmail in {browser}', action_type='WEB_NAVIGATE', tool='browser', args={'url': 'https://mail.google.com'}, expected_outcome={'url_contains': 'mail.google.com'})])

    if t.startswith('summarize unread emails'):
        return _build_plan(goal='Read and summarize unread Gmail emails', signature=intent_signature(text), steps=[Step(id='s1', name='Read Gmail unread', action_type='WEB_READ', tool='browser', args={'target': 'gmail_unread'}, expected_outcome={'unread_count_gte': 0})])

    if t.startswith('search '):
        q = re.sub(r'\s+and give me key points$', '', text[7:], flags=re.I)
        return _build_plan(goal=f'Search the web for {q} and return key points', signature=intent_signature(text), steps=[Step(id='s1', name='Search web', action_type='WEB_READ', tool='browser', args={'target': 'search', 'query': q}, expected_outcome={'key_points_gte': 1})], context={'query': q}, success_criteria=[{'type': 'key_points_gte', 'expected': 1}], slots={'query': q})

    if t.startswith('find flights from'):
        m = re.search(r'find flights from\s+(\S+)\s+to\s+(\S+)\s+on\s+([^\s]+)\s+return\s+([^\s]+)', t)
        args = {'target': 'flights', 'query': text}
        slots = {}
        if m:
            slots = {'origin': m.group(1).upper(), 'dest': m.group(2).upper(), 'depart': m.group(3), 'return': m.group(4)}
            args.update(slots)
        return _build_plan(goal='Search flights matching the requested itinerary', signature=intent_signature(text), steps=[Step(id='s1', name='Search flights', action_type='WEB_READ', tool='browser', args=args, expected_outcome={'flights_gte': 1})], context=slots, success_criteria=[{'type': 'flights_gte', 'expected': 1}], slots=slots)

    return _build_plan(goal='Echo unsupported command for debugging', signature=intent_signature(text), steps=[Step(id='s1', name='Noop', action_type='NOOP', tool='control', args={'echo': text}, expected_outcome={'ok': True})])
