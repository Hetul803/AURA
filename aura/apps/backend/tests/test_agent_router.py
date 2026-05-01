from fastapi.testclient import TestClient

from api.main import app
from aura.agent_router import diagnose_breakage, list_agents, route_agent, workflow_suggestions
from aura.orchestrator import run_command
from aura.planner import plan_from_text
from aura.state import db_conn
from storage.db import init_db
from tools.agent_worker import handle_agent_action

client = TestClient(app)


def _clear_workflow_memory():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM workflow_memory')
        conn.execute('DELETE FROM memory_items')


def test_agent_registry_and_local_coding_route(monkeypatch):
    monkeypatch.delenv('AURA_CODEX_ENABLED', raising=False)
    monkeypatch.delenv('CODEX_HOME', raising=False)

    agents = {agent['agent_id']: agent for agent in list_agents()}
    assert agents['local-code-worker']['status'] == 'available'
    assert agents['codex-coding-agent']['role'] == 'coding'

    route = route_agent(task='fix this bug and run tests', task_type='code:python_script', context={'workspace': 'repo'})
    assert route['agent_id'] == 'local-code-worker'
    assert 'Required loop' in route['agent_prompt']
    assert 'protect secrets' in route['agent_prompt']


def test_codex_route_when_configured_for_large_coding_task(monkeypatch):
    monkeypatch.setenv('AURA_CODEX_ENABLED', '1')

    route = route_agent(task='build me an app with frontend and backend', task_type='agent:coding', context={'workspace': 'repo'})

    assert route['agent_id'] == 'codex-coding-agent'
    assert route['status'] == 'available'
    assert 'build me an app' in route['agent_prompt']


def test_diagnose_breakage_identifies_repairable_failure():
    diagnosis = diagnose_breakage({
        'failure_class': 'name_error',
        'failure_detail': "name 'pritn' is not defined",
        'traceback_excerpt': 'NameError: pritn',
        'repairable': True,
    })

    assert diagnosis['failure_class'] == 'name_error'
    assert diagnosis['repairable'] is True
    assert 'missing or misspelled symbol' in diagnosis['recommended_action']


def test_agent_delegate_tool_returns_prompt(monkeypatch):
    monkeypatch.delenv('AURA_CODEX_ENABLED', raising=False)
    monkeypatch.delenv('CODEX_HOME', raising=False)

    class Step:
        action_type = 'AGENT_DELEGATE'
        name = 'Delegate coding task'
        args = {'task': 'repair aura tests', 'task_type': 'agent:coding', 'context': {'workspace': 'aura'}}

    result = handle_agent_action(Step(), {})

    assert result['ok'] is True
    assert result['observation']['agent_id'] == 'local-code-worker'
    assert result['result']['agent_prompt']


def test_planner_routes_app_creation_to_agent_delegate(monkeypatch):
    monkeypatch.delenv('AURA_CODEX_ENABLED', raising=False)
    monkeypatch.delenv('CODEX_HOME', raising=False)

    plan = plan_from_text('Create a full app for this idea', context={'workspace_hint': 'C:/demo'})

    assert plan['signature'] == 'agent:coding'
    assert plan['steps'][0].action_type == 'AGENT_DELEGATE'
    assert plan['context']['agent_route']['agent_id'] == 'local-code-worker'


def test_command_executes_agent_route_and_learning():
    result = run_command('Create a full app for this idea', context={'workspace_hint': 'C:/demo'})

    assert result['ok'] is True
    assert result['steps'][0]['status'] == 'success'
    route = result['steps'][0]['result']['result']['route']
    assert route['agent_prompt']
    assert result['run_state']['plan']['signature'] == 'agent:coding'


def test_agent_api_and_workflow_suggestions():
    _clear_workflow_memory()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO workflow_memory(task_type, pattern_key, strategy, confidence, success_count, failure_count, notes)
            VALUES(?,?,?,?,?,?,?)
            ''',
            ('agent:coding', 'agent:local-code-worker', 'route_agent_and_prompt_worker', 0.76, 2, 0, 'worked twice'),
        )

    assert client.get('/agents').status_code == 200
    assert client.get('/agents/local-code-worker').json()['role'] == 'coding'
    routed = client.post('/agents/route', json={'task': 'fix failing tests', 'task_type': 'agent:coding'})
    assert routed.status_code == 200
    assert routed.json()['agent_prompt']

    suggestions = workflow_suggestions()
    assert suggestions[0]['automation_ready'] is True
    api_suggestions = client.get('/agents/workflow-suggestions')
    assert api_suggestions.status_code == 200
    assert api_suggestions.json()[0]['strategy'] == 'route_agent_and_prompt_worker'
