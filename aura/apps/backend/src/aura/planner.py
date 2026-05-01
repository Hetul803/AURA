from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .agent_router import route_agent
from .assist import classify_assist_task, looks_like_assist_request, research_mode_for, style_hints_for
from .context_engine import default_workspace_root, github_repo_from_url
from .learning import query_relevant_memory
from .memory import execution_hints, latest_memory
from .prefs import get_pref_value, should_ask
from .steps import Condition, RetryPolicy, Step
from .user_tools import build_user_ai_prompt, infer_user_tool


def intent_signature(text: str) -> str:
    t = text.lower().strip()
    if 'clone' in t and ('repo' in t or 'repository' in t or 'this' in t):
        return 'github:clone'
    if t.startswith('fix and run python script at') or t.startswith('run python script at'):
        return 'code:python_script'
    if 'open cursor' in t:
        return 'cursor:os'
    coding_build_signal = any(phrase in t for phrase in ['build', 'create', 'make', 'implement', 'scaffold'])
    coding_artifact_signal = any(token in t for token in ['app', 'saas', 'landing page', 'website', 'frontend', 'backend', 'repo', 'codebase'])
    if any(phrase in t for phrase in ['use codex', 'ask codex', 'delegate to codex', 'create a full app', 'repair aura', 'fix aura']) or (coding_build_signal and coding_artifact_signal):
        return 'agent:coding'
    if any(token in t for token in ['chatgpt', 'claude']) or 'use my ai subscription' in t:
        return 'user_ai:web'
    if t.startswith('search '):
        return 'search:web'
    if 'gmail' in t:
        return 'gmail:web'
    if t.startswith('find flights from'):
        return 'flights:web'
    if looks_like_assist_request(text):
        return 'assist:writing'
    if 'open this folder' in t or 'open this file' in t:
        return 'open_path:os'
    return 'generic:noop'


def _domain_from_steps(steps: list[Step]) -> str | None:
    for step in steps:
        url = (step.args or {}).get('url')
        if url:
            return urlparse(url).netloc or None
    return None


def _gmail_clarifications(choices: dict | None = None) -> list[dict]:
    asks = []
    supplied = choices or {}
    for key, options in {
        'gmail.browser': ['Default', 'Chrome', 'Safari'],
        'gmail.mode': ['Web', 'App'],
        'gmail.account': ['Primary', 'Other'],
    }.items():
        if key not in supplied and should_ask(key):
            asks.append({'key': key, 'options': options})
    return asks


def _build_plan(*, goal: str, signature: str, steps: list[Step], context: dict | None = None,
                success_criteria: list[dict] | None = None, clarifications: list[dict] | None = None,
                memory_scope: str | None = None, slots: dict | None = None, assist: dict | None = None) -> dict:
    scope = memory_scope or signature
    plan_context = context or {}
    domain = _domain_from_steps(steps)
    learning_hints = query_relevant_memory(task_type=signature, domain=domain)
    return {
        'goal': goal,
        'signature': signature,
        'context': plan_context,
        'assist': assist or {},
        'steps': steps,
        'success_criteria': success_criteria or [],
        'clarifications': clarifications or [],
        'memory_hints': execution_hints(scope),
        'learning_hints': learning_hints,
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
    context = {
        'script_path': path,
        'workspace': workspace,
        'last_success_hint': last_success['value'] if last_success else None,
    }
    context['agent_route'] = route_agent(task=text, task_type=signature, context=context)
    success_criteria = [{'type': 'exit_code', 'expected': 0}, {'type': 'artifact_exists', 'expected': path}]
    return _build_plan(
        goal=f'Execute and, if needed, repair the Python script at {path}',
        signature=signature,
        steps=steps,
        context=context,
        success_criteria=success_criteria,
        memory_scope=f'script:{path}',
    )


def _agent_coding_plan(text: str, context: dict | None = None) -> dict:
    route = route_agent(task=text, task_type='agent:coding', context=context or {})
    steps = [
        Step(
            id='s1',
            name='Route coding work to best agent',
            action_type='AGENT_DELEGATE',
            tool='agent',
            args={'task': text, 'task_type': 'agent:coding', 'context': context or {}},
            expected_outcome={'ok': True},
        ),
    ]
    return _build_plan(
        goal='Route coding or self-repair work to the best available agent',
        signature='agent:coding',
        steps=steps,
        context={'request_text': text, 'agent_route': route, 'context_snapshot': context or {}},
        success_criteria=[{'type': 'agent_route_ready', 'expected': True}],
        memory_scope='agent:coding',
        slots={'agent_id': route['agent_id']},
    )


def _mode_for_user_ai(text: str) -> str:
    low = text.lower()
    if any(token in low for token in ['email', 'reply', 'gmail']):
        return 'email'
    if any(token in low for token in ['code', 'app', 'cursor', 'repo', 'bug']):
        return 'coding'
    return 'general'


def _user_ai_web_plan(text: str, context: dict | None = None) -> dict:
    tool_id = infer_user_tool(text)
    mode = _mode_for_user_ai(text)
    prepared = build_user_ai_prompt(task=text, tool_id=tool_id, context=context or {}, mode=mode)
    tool = prepared['tool']
    prompt = prepared['prompt']
    domain = tool['url'].split('//', 1)[1].split('/', 1)[0]
    steps = [
        Step(
            id='s1',
            name='Prepare prompt for user AI tool',
            action_type='USER_AI_PREPARE_PROMPT',
            tool='agent',
            args={'task': text, 'tool_id': tool_id, 'mode': mode, 'context': context or {}},
            expected_outcome={'prompt_ready': True},
        ),
        Step(
            id='s2',
            name=f"Open {tool['label']}",
            action_type='WEB_NAVIGATE',
            tool='browser',
            args={'url': tool['url']},
            expected_outcome={'url_contains': domain},
        ),
        Step(
            id='s3',
            name='Copy prepared prompt to clipboard',
            action_type='OS_WRITE_CLIPBOARD',
            tool='os',
            args={'text': prompt},
            expected_outcome={'written_gte': min(20, len(prompt))},
        ),
        Step(
            id='s4',
            name=f"Paste prompt into {tool['label']}",
            action_type='OS_PASTE',
            tool='os',
            args={'text': prompt, 'cautious': True},
            expected_outcome={'pasted_gte': min(20, len(prompt))},
            safety_level='CONFIRM',
        ),
    ]
    return _build_plan(
        goal=f"Use the user's {tool['label']} subscription for the requested task",
        signature='user_ai:web',
        steps=steps,
        context={'request_text': text, 'tool': tool, 'mode': mode, 'prepared_prompt': prepared, 'context_snapshot': context or {}},
        success_criteria=[{'type': 'prompt_ready', 'expected': True}, {'type': 'approval_received', 'expected': True}],
        memory_scope=f'user_ai:{tool_id}:{mode}',
        slots={'tool_id': tool_id, 'mode': mode},
    )


def _context_ref(context: dict | None, ref_type: str) -> dict | None:
    for ref in (context or {}).get('context_refs', []):
        if ref.get('type') == ref_type:
            return ref
    return None


def _clone_github_repo_plan(text: str, context: dict | None = None) -> dict:
    github_ref = _context_ref(context, 'github_repo') or github_repo_from_url((context or {}).get('browser_url'))
    if not github_ref:
        return _build_plan(
            goal='Clone the GitHub repository the user is looking at',
            signature='github:clone',
            steps=[],
            context={'request_text': text, 'context_snapshot': context or {}},
            clarifications=[{'key': 'github.repo_url', 'options': ['Paste GitHub repo URL']}],
        )

    workspace_root = (context or {}).get('workspace_hint') or default_workspace_root()
    target_path = str(Path(workspace_root).expanduser() / github_ref['repo'])
    command = f'git clone "{github_ref["clone_url"]}" "{target_path}"'
    steps = [
        Step(
            id='s1',
            name='Clone GitHub repository',
            action_type='CODE_RUN',
            tool='code',
            args={'kind': 'shell', 'command': command, 'workspace': workspace_root},
            expected_outcome={'exit_code': 0},
            safety_level='CONFIRM',
            fallback_hint='ask_for_git_or_folder_fix',
        ),
        Step(
            id='s2',
            name='Verify cloned repository folder',
            action_type='FS_EXISTS',
            tool='filesystem',
            args={'path': target_path},
            expected_outcome={'exists': True},
            postconditions=[Condition(type='bool', key='file_exists', expected=True)],
        ),
    ]
    return _build_plan(
        goal=f"Clone {github_ref['repo_full_name']} locally",
        signature='github:clone',
        steps=steps,
        context={
            'request_text': text,
            'context_snapshot_id': (context or {}).get('snapshot_id'),
            'source_browser_url': (context or {}).get('browser_url'),
            'github_repo': github_ref,
            'workspace_root': workspace_root,
            'target_path': target_path,
            'implicit_context_used': True,
        },
        success_criteria=[{'type': 'exit_code', 'expected': 0}, {'type': 'path_opened', 'expected': target_path}],
        memory_scope=f"github:{github_ref['repo_full_name']}",
        slots={'repo': github_ref['repo_full_name'], 'target_path': target_path},
    )


def _assist_plan(text: str) -> dict:
    intent = classify_assist_task(text)
    task_kind = intent['task_kind']
    style_hints = {**style_hints_for(task_kind), **(intent.get('style_hints') or {})}
    research_mode = research_mode_for(task_kind, intent['needs_research'])
    task_goal = {
        'summarize': 'Summarize the captured text clearly',
        'reply': 'Draft a helpful reply to the captured text',
        'rewrite': 'Rewrite the captured text naturally and clearly',
        'explain': 'Explain the captured text clearly',
        'answer': 'Answer the captured question or request',
        'research_and_respond': 'Research the captured request and produce a grounded response',
    }.get(task_kind, 'Draft a response to the captured text')
    steps = [Step(id='s1', name='Capture active context', action_type='ASSIST_CAPTURE_CONTEXT', tool='assist', expected_outcome={'ok': True})]
    if research_mode != 'none':
        steps.append(Step(id='s2', name='Gather bounded context', action_type='ASSIST_RESEARCH_CONTEXT', tool='assist', args={'research_mode': research_mode}, expected_outcome={'ok': True}))
        draft_id, approval_id, paste_id = 's3', 's4', 's5'
    else:
        draft_id, approval_id, paste_id = 's2', 's3', 's4'
    steps.extend([
        Step(id=draft_id, name='Generate model-backed draft', action_type='ASSIST_DRAFT', tool='assist', expected_outcome={'ok': True}),
        Step(id=approval_id, name='Wait for approval', action_type='ASSIST_WAIT_APPROVAL', tool='assist', expected_outcome={'ok': True}, safety_level='CONFIRM'),
        Step(id=paste_id, name='Paste approved result back', action_type='ASSIST_PASTE_BACK', tool='assist', expected_outcome={'pasted_gte': 1}, safety_level='CONFIRM'),
    ])
    assist = {
        'task_kind': task_kind,
        'source_text_present': intent['source_text_present'],
        'intent_confidence': intent['intent_confidence'],
        'needs_research': intent['needs_research'],
        'research_mode': research_mode,
        'style_hints': style_hints,
        'approval_required': True,
        'pasteback_mode': intent['pasteback_mode'],
        'target_behavior': 'paste_back',
        'source_requirement': 'selection_or_clipboard',
        'classifier': {
            'provider': intent.get('provider'),
            'model': intent.get('model'),
            'fallback_used': intent.get('fallback_used', False),
            'reasoning_summary': intent.get('reasoning_summary', ''),
        },
    }
    context = {
        'request_text': text,
        'intent': task_kind,
        'intent_confidence': intent['intent_confidence'],
        'source_text_present': intent['source_text_present'],
        'needs_research': intent['needs_research'],
        'approval_required': True,
        'style_hints': style_hints,
        'pasteback': {'mode': intent['pasteback_mode']},
    }
    success_criteria = [
        {'type': 'captured_input_present', 'expected': True},
        {'type': 'draft_ready', 'expected': True},
        {'type': 'approval_received', 'expected': True},
        {'type': 'draft_pasted', 'expected': True},
    ]
    return _build_plan(goal=f'{task_goal} and paste it back after approval', signature='assist:writing', steps=steps, context=context, success_criteria=success_criteria, assist=assist)


def plan_from_text(text: str, choices: dict | None = None, context: dict | None = None) -> dict:
    t = text.lower().strip()

    if intent_signature(text) == 'github:clone':
        return _clone_github_repo_plan(text, context)

    if t.startswith('fix and run python script at') or t.startswith('run python script at'):
        return _code_plan(text)

    if intent_signature(text) == 'agent:coding':
        return _agent_coding_plan(text, context)

    if intent_signature(text) == 'user_ai:web':
        return _user_ai_web_plan(text, context)

    if t.startswith('take the selected text, search it'):
        return _build_plan(
            goal='Capture selected text, research it on the web, and return key points',
            signature='selection:web',
            steps=[
                Step(id='s1', name='Copy selected text', action_type='OS_COPY_SELECTION', tool='os', expected_outcome={'clipboard_length_gte': 1}),
                Step(id='s2', name='Search selected text', action_type='WEB_READ', tool='browser', args={'target': 'search', 'query': '__FROM_CLIPBOARD__'}, expected_outcome={'key_points_gte': 1}),
            ],
            success_criteria=[{'type': 'key_points_gte', 'expected': 1}],
        )

    if intent_signature(text) == 'assist:writing':
        return _assist_plan(text)

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
        clarifications = _gmail_clarifications(choices)
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
