from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.main import app
from aura.state import db_conn
from storage.db import init_db
from tools.tool_result import success

client = TestClient(app)


def _clear_tables():
    init_db()
    with db_conn() as conn:
        for table in [
            'reflection_records',
            'workflow_memory',
            'preference_memory',
            'site_memory',
            'safety_memory',
            'memories',
            'preferences',
            'macros',
        ]:
            conn.execute(f'DELETE FROM {table}')


def _patch_assist(monkeypatch):
    from aura import assist

    monkeypatch.setattr(assist, 'classify_assist_request', lambda text: SimpleNamespace(
        task_kind='reply', source_text_present=True, intent_confidence=0.88, needs_research=False,
        style_hints={'tone': 'polished', 'length': 'concise'}, approval_required=True,
        pasteback_mode='reactivate_validate_paste', reasoning_summary='mocked', provider='ollama', model='qwen2.5:3b', fallback_used=False,
    ))
    monkeypatch.setattr(assist, 'capture_context', lambda: {
        'ok': True,
        'active_app': 'Mail',
        'window_title': 'Inbox',
        'browser_url': 'https://mail.example.com',
        'browser_title': 'Inbox',
        'selected_text': 'Please send an update.',
        'clipboard_text': '',
        'input_text': 'Please send an update.',
        'input_source': 'selected_text',
        'capture_method': {'selected_text_attempted': True, 'selected_text_succeeded': True, 'clipboard_fallback_used': False},
        'paste_target': {'app_name': 'Mail', 'window_title': 'Inbox', 'target_url': 'https://mail.example.com', 'target_domain': 'mail.example.com', 'browser_title': 'Inbox', 'captured_at': '2026-03-18T00:00:00Z'},
        'warnings': [],
    })
    monkeypatch.setattr(assist, 'handle_web_action', lambda step: success('WEB_READ', result={'key_points': ['One source-backed note.'], 'sources': ['https://mail.example.com']}))
    monkeypatch.setattr(assist, 'generate_assist_draft', lambda **kwargs: SimpleNamespace(
        draft_text='Natural reply draft',
        style_signals_used=dict(kwargs['style_hints']),
        research_used=False,
        provider='ollama',
        model='qwen2.5:3b',
        fallback_used=False,
        confidence=0.82,
        notes=['mocked_provider'],
    ))
    monkeypatch.setattr(assist, 'restore_target_and_paste', lambda text, target, strict=False: success('OS_PASTE', result={'pasted': len(text)}, observation={'target_validation': 'target_valid', 'strict_validation': strict}))


def test_assist_context_endpoint(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)

    response = client.post('/assist/context')

    assert response.status_code == 200
    assert response.json()['input_text'] == 'Please send an update.'


def test_approve_retry_and_reject_flow_visible_in_run_state(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)

    run = client.post('/command', json={'text': 'Draft a reply to this'})
    assert run.status_code == 200
    body = run.json()
    assert body['status'] == 'awaiting_approval'
    run_id = body['run_id']

    state = client.get(f'/runs/{run_id}')
    assert state.status_code == 200
    assert state.json()['captured_context']['active_app'] == 'Mail'
    assert state.json()['approval_state']['status'] == 'pending'
    assert state.json()['assist']['generation']['provider'] == 'ollama'

    retried = client.post(f'/runs/{run_id}/retry', json={'feedback': 'make it more direct'})
    assert retried.status_code == 200
    assert retried.json()['status'] == 'awaiting_approval'
    assert retried.json()['run_state']['draft_state']['style_hints']['tone'] == 'direct'

    approved = client.post(f'/runs/{run_id}/approve', json={'text': 'Approved API draft'})
    assert approved.status_code == 200
    assert approved.json()['ok'] is True
    final_state = client.get(f'/runs/{run_id}').json()
    assert final_state['approval_state']['status'] == 'pasted'
    assert final_state['pasteback_state']['status'] == 'pasted'

    second = client.post('/command', json={'text': 'Summarize this'}).json()
    rejected = client.post(f"/runs/{second['run_id']}/reject", json={'reason': 'not needed'})
    assert rejected.status_code == 200
    assert rejected.json()['status'] == 'rejected'
