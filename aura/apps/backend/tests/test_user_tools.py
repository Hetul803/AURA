from fastapi.testclient import TestClient

from api.main import app
from aura.planner import intent_signature, plan_from_text
from aura.user_tools import build_user_ai_prompt, infer_user_tool, list_user_web_tools
from tools.user_ai import handle_user_ai_action

client = TestClient(app)


def test_user_tool_registry_and_prompt_builder():
    tools = {tool['tool_id']: tool for tool in list_user_web_tools()}
    assert tools['chatgpt']['url'].startswith('https://chatgpt.com')
    assert tools['claude']['url'].startswith('https://claude.ai')
    assert infer_user_tool('Ask Claude to improve this') == 'claude'

    prepared = build_user_ai_prompt(
        task='Draft a reply to this email',
        tool_id='chatgpt',
        mode='email',
        context={'input_text': 'Professor: can you send the report?', 'browser_url': 'https://mail.google.com/mail/u/0/#inbox'},
    )
    assert prepared['tool']['tool_id'] == 'chatgpt'
    assert 'draft only; do not send' in prepared['prompt']
    assert 'Professor' in prepared['prompt']


def test_user_ai_prepare_prompt_tool():
    class Step:
        action_type = 'USER_AI_PREPARE_PROMPT'
        name = 'Prepare prompt'
        args = {'task': 'Use Claude to summarize this', 'tool_id': 'claude', 'context': {'input_text': 'Source text'}, 'mode': 'general'}

    result = handle_user_ai_action(Step(), {})

    assert result['ok'] is True
    assert result['observation']['prompt_ready'] is True
    assert result['observation']['tool_id'] == 'claude'
    assert 'Source text' in result['result']['prompt']


def test_planner_creates_user_subscription_browser_handoff_plan():
    plan = plan_from_text('Use ChatGPT to draft a reply to this email', context={
        'input_text': 'Client asks for pricing.',
        'browser_url': 'https://mail.google.com',
    })

    assert intent_signature('Use ChatGPT to draft a reply to this email') == 'user_ai:web'
    assert plan['signature'] == 'user_ai:web'
    assert plan['context']['tool']['tool_id'] == 'chatgpt'
    assert plan['context']['mode'] == 'email'
    assert [step.action_type for step in plan['steps']] == ['USER_AI_PREPARE_PROMPT', 'WEB_NAVIGATE', 'OS_WRITE_CLIPBOARD', 'OS_PASTE']
    assert plan['steps'][-1].safety_level == 'CONFIRM'
    assert 'Client asks for pricing.' in plan['context']['prepared_prompt']['prompt']


def test_user_tool_api_contracts():
    listed = client.get('/user-tools')
    assert listed.status_code == 200
    assert any(tool['tool_id'] == 'chatgpt' for tool in listed.json())

    claude = client.get('/user-tools/claude')
    assert claude.status_code == 200
    assert claude.json()['provider'] == 'anthropic'

    missing = client.get('/user-tools/missing')
    assert missing.status_code == 404

    prompt = client.post('/user-tools/prompt', json={
        'task': 'Use ChatGPT for a Cursor prompt',
        'tool_id': 'chatgpt',
        'mode': 'coding',
        'context': {'input_text': 'Build a SaaS landing page.'},
    })
    assert prompt.status_code == 200
    assert 'coding agent can execute' in prompt.json()['prompt']
