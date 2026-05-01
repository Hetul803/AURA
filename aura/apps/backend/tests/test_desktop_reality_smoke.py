from fastapi.testclient import TestClient

from api.main import app
from aura.state import db_conn

client = TestClient(app)


def _github_context() -> dict:
    return {
        'source': 'desktop-smoke',
        'active_app': 'Chrome',
        'window_title': 'Hetul803/AURA: repo',
        'browser_url': 'https://github.com/Hetul803/AURA',
        'browser_title': 'GitHub - Hetul803/AURA',
        'selected_text': '',
        'clipboard_text': '',
        'workspace_hint': 'C:/Users/aura/workspaces',
    }


def test_clone_this_repo_uses_browser_context_and_requires_approval():
    body = client.post('/command', json={'text': 'clone this repo locally', 'context': _github_context()}).json()

    assert body['ok'] is False
    assert body['status'] == 'awaiting_approval'
    assert body['run_state']['plan']['signature'] == 'github:clone'
    approval = body['run_state']['approval_state']
    assert approval['kind'] == 'tool_confirmation'
    assert approval['action_type'] == 'CODE_RUN'
    assert 'git clone' in approval['requested_args']['command']
    assert 'https://github.com/Hetul803/AURA.git' in approval['requested_args']['command']


def test_email_reply_entrypoint_plans_approval_and_pasteback():
    plan = client.post('/plan', json={'text': 'Reply to this email'}).json()

    assert plan['signature'] == 'assist:writing'
    assert plan['assist']['task_kind'] == 'reply'
    assert plan['assist']['approval_required'] is True
    actions = [step['action_type'] for step in plan['steps']]
    assert 'ASSIST_WAIT_APPROVAL' in actions
    assert actions[-1] == 'ASSIST_PASTE_BACK'


def test_email_reply_command_uses_supplied_desktop_context_for_draft():
    body = client.post('/command', json={
        'text': 'Reply to this email',
        'context': {
            'active_app': 'Chrome',
            'browser_url': 'https://mail.google.com/mail/u/0/#inbox/abc',
            'browser_title': 'Question from Professor - Gmail',
            'selected_text': 'Can you send the report by 5 PM today?',
            'input_source': 'selected_text',
        },
    }).json()

    assert body['ok'] is False
    assert body['status'] == 'awaiting_approval'
    state = body['run_state']
    assert state['captured_context']['input_text'] == 'Can you send the report by 5 PM today?'
    assert state['captured_context']['browser_domain'] == 'mail.google.com'
    assert state['draft_state']['task_kind'] == 'reply'
    assert state['approval_state']['draft_text']


def test_saas_landing_page_entrypoint_routes_to_coding_agent_not_noop():
    with db_conn() as conn:
        conn.execute('DELETE FROM macros')

    body = client.post('/command', json={
        'text': 'Build me a SaaS landing page for this idea',
        'context': {'workspace_hint': 'C:/Users/aura/workspaces/new-saas'},
    }).json()

    assert body['ok'] is True
    assert body['run_state']['plan']['signature'] == 'agent:coding'
    assert body['steps'][0]['status'] == 'success'
    route = body['steps'][0]['result']['result']['route']
    assert route['agent_id'] in {'local-code-worker', 'codex-coding-agent'}
    assert route['agent_prompt']


def test_user_subscription_handoff_prepares_prompt_and_stops_before_paste():
    body = client.post('/command', json={
        'text': 'Use my ChatGPT subscription to write a reply to this email',
        'context': {'selected_text': 'Can you send the report today?', 'active_app': 'Chrome'},
    }).json()

    assert body['ok'] is False
    assert body['status'] == 'awaiting_approval'
    assert body['run_state']['plan']['signature'] == 'user_ai:web'
    approval = body['run_state']['approval_state']
    assert approval['action_type'] == 'OS_PASTE'
    assert approval['tool'] == 'os'
    assert 'ChatGPT' in body['run_state']['plan']['context']['tool']['label']


def test_workflow_suggestion_can_be_saved_and_rendered():
    with db_conn() as conn:
        conn.execute('DELETE FROM workflow_templates')
        conn.execute('DELETE FROM workflow_memory')
        conn.execute(
            '''
            INSERT INTO workflow_memory(task_type, pattern_key, strategy, confidence, success_count, failure_count, notes)
            VALUES(?,?,?,?,?,?,?)
            ''',
            ('assist:writing', 'task_kind:reply', 'capture_draft_approve_paste', 0.82, 3, 0, 'reply worked'),
        )

    suggestions = client.get('/workflows/suggestions').json()
    assert suggestions
    suggestion = suggestions[0]
    created = client.post('/workflows', json={
        'name': suggestion['suggested_workflow_name'],
        'description': suggestion['description'],
        'command_template': suggestion['command_template'],
        'trigger_type': suggestion['trigger_type'],
        'trigger_value': suggestion['trigger_value'],
        'source': suggestion['source'],
        'confidence': suggestion['confidence'],
    }).json()
    rendered = client.post(f"/workflows/{created['workflow_id']}/render", json={'variables': {}}).json()

    assert rendered['command'] == 'Draft a reply to this'
