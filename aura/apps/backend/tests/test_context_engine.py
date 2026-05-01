from fastapi.testclient import TestClient

from api.main import app
from aura.context_engine import github_repo_from_url, list_context_snapshots, normalize_context, persist_context_snapshot
from aura.orchestrator import run_command
from aura.planner import plan_from_text
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_context_tables():
    init_db()
    with db_conn() as conn:
        for table in ['context_snapshots', 'run_records', 'run_events', 'approval_records', 'audit_log', 'reflection_records', 'workflow_memory', 'preference_memory', 'site_memory', 'safety_memory', 'macros']:
            conn.execute(f'DELETE FROM {table}')


def _github_context():
    return normalize_context({
        'ok': True,
        'active_app': 'Google Chrome',
        'window_title': 'Hetul803/AURA: personal AI OS',
        'browser_url': 'https://github.com/Hetul803/AURA/tree/main/aura',
        'browser_title': 'GitHub - Hetul803/AURA',
        'selected_text': '',
        'clipboard_text': '',
        'input_text': '',
        'input_source': 'none',
        'current_folder': '.',
    }, source='test')


def test_github_repo_reference_is_extracted_from_active_browser_url():
    ref = github_repo_from_url('https://github.com/Hetul803/AURA/issues/1')

    assert ref is not None
    assert ref['repo_full_name'] == 'Hetul803/AURA'
    assert ref['clone_url'] == 'https://github.com/Hetul803/AURA.git'


def test_context_snapshot_persists_normalized_desktop_signals():
    _clear_context_tables()
    snapshot = persist_context_snapshot(_github_context())

    rows = list_context_snapshots()

    assert rows[0]['snapshot_id'] == snapshot['snapshot_id']
    assert rows[0]['browser_domain'] == 'github.com'
    assert rows[0]['context_refs'][0]['repo_full_name'] == 'Hetul803/AURA'
    assert rows[0]['privacy']['local_first'] is True


def test_context_api_captures_current_snapshot(monkeypatch):
    _clear_context_tables()
    from aura import context_engine

    monkeypatch.setattr(context_engine, 'capture_context', lambda: {
        'ok': True,
        'active_app': 'Arc',
        'window_title': 'GitHub',
        'browser_url': 'https://github.com/Hetul803/AURA',
        'browser_title': 'AURA',
        'input_text': '',
        'input_source': 'none',
        'current_folder': '.',
    })

    response = client.get('/context/current')

    assert response.status_code == 200
    body = response.json()
    assert body['context_refs'][0]['repo_full_name'] == 'Hetul803/AURA'
    assert client.get('/context/latest').json()['snapshot_id'] == body['snapshot_id']


def test_clone_this_repo_plan_uses_context_without_user_pasting_url():
    context = _github_context()

    plan = plan_from_text('clone this repo locally', context=context)

    assert plan['signature'] == 'github:clone'
    assert plan['context']['github_repo']['repo_full_name'] == 'Hetul803/AURA'
    assert plan['context']['implicit_context_used'] is True
    assert plan['steps'][0].action_type == 'CODE_RUN'
    assert plan['steps'][0].safety_level == 'CONFIRM'
    assert 'git clone "https://github.com/Hetul803/AURA.git"' in plan['steps'][0].args['command']


def test_clone_this_repo_run_pauses_for_approval_before_shell_dispatch():
    _clear_context_tables()
    context = _github_context()

    run = run_command('clone this repo locally', context=context)

    assert run['status'] == 'awaiting_approval'
    assert run['run_state']['planning_context']['context_refs'][0]['repo_full_name'] == 'Hetul803/AURA'
    assert run['run_state']['approval_state']['action_type'] == 'CODE_RUN'
    assert 'git clone' in run['run_state']['approval_state']['requested_args']['command']
