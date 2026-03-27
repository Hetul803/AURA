from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.main import app
from aura.state import db_conn
from storage.db import init_db
from tools.tool_result import failure, success

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
        'capture_path_used': 'selected_text',
        'capture_method': {'selection_copy_attempted': True, 'selection_copy_succeeded': True, 'clipboard_fallback_used': False, 'clipboard_preserved': True, 'clipboard_restored_after_capture': True, 'capture_failure_reason': None},
        'target_fingerprint': {'app_name': 'Mail', 'window_title': 'Inbox', 'browser_url': 'https://mail.example.com', 'browser_domain': 'mail.example.com', 'browser_title': 'Inbox', 'captured_at': '2026-03-18T00:00:00Z', 'capture_path_used': 'selected_text', 'normalized': {'app_name': 'mail', 'window_title': 'inbox', 'browser_url': 'https://mail.example.com', 'browser_domain': 'mail.example.com', 'browser_title': 'inbox'}},
        'paste_target': {'app_name': 'Mail', 'window_title': 'Inbox', 'browser_url': 'https://mail.example.com', 'browser_domain': 'mail.example.com', 'browser_title': 'Inbox', 'captured_at': '2026-03-18T00:00:00Z', 'capture_path_used': 'selected_text', 'normalized': {'app_name': 'mail', 'window_title': 'inbox', 'browser_url': 'https://mail.example.com', 'browser_domain': 'mail.example.com', 'browser_title': 'inbox'}},
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
    monkeypatch.setattr(assist, 'restore_target_and_paste', lambda text, target, strict=False, cautious=False: success('OS_PASTE', result={'pasted': len(text)}, observation={'target_validation': 'exact_match', 'target_validation_result': 'exact_match', 'strict_validation': strict, 'cautious_validation': cautious, 'paste_attempted': True, 'clipboard_preserved': True, 'clipboard_restored_after_paste': True, 'paste_blocked_reason': None, 'context_drift_reason': None, 'target_fingerprint': target}))


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
    assert state.json()['captured_context']['capture_path_used'] == 'selected_text'
    assert state.json()['assist']['target_fingerprint']['browser_domain'] == 'mail.example.com'

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
    assert final_state['pasteback_state']['target_validation_result'] == 'exact_match'
    assert final_state['pasteback_state']['clipboard_restored_after_paste'] is True

    second = client.post('/command', json={'text': 'Summarize this'}).json()
    rejected = client.post(f"/runs/{second['run_id']}/reject", json={'reason': 'not needed'})
    assert rejected.status_code == 200
    assert rejected.json()['status'] == 'rejected'


def test_paste_failure_reason_is_visible_via_run_state(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)
    from aura import assist

    monkeypatch.setattr(assist, 'restore_target_and_paste', lambda text, target, strict=False, cautious=False: failure('OS_PASTE', error='paste_target_changed', observation={'failure_class': 'paste_target_changed', 'failure_detail': 'browser_domain_changed', 'target_validation_result': 'drifted', 'target_validation': 'active_app_changed', 'paste_attempted': False, 'paste_blocked_reason': 'target_drift_detected', 'context_drift_reason': 'browser_domain_changed', 'clipboard_restored_after_paste': True, 'strict_validation': strict, 'cautious_validation': cautious, 'target_fingerprint': target}, requires_user=True, retryable=True, result={'pasted': 0}))

    run = client.post('/command', json={'text': 'Draft a reply to this'}).json()
    approved = client.post(f"/runs/{run['run_id']}/approve", json={'text': 'Approved API draft'})

    assert approved.status_code == 200
    assert approved.json()['status'] == 'needs_user'
    state = client.get(f"/runs/{run['run_id']}").json()
    assert state['pasteback_state']['target_validation_result'] == 'drifted'
    assert state['pasteback_state']['paste_blocked_reason'] == 'target_drift_detected'
    assert state['pasteback_state']['context_drift_reason'] == 'browser_domain_changed'


def test_assist_personalization_and_suggestions_endpoints(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO preference_memory(scope, memory_key, value, confidence, evidence_count, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
            ('assist:writing|app:mail', 'writing.tone', 'polished', 0.84, 4, '2026-03-19T00:00:00Z'),
        )
        conn.execute(
            "INSERT INTO workflow_memory(task_type, pattern_key, strategy, confidence, success_count, failure_count, last_seen, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ('assist:writing', 'approval:unchanged', 'explicit_review_before_paste', 0.8, 3, 0, '2026-03-19T00:00:00Z', ''),
        )

    personalization = client.post('/assist/personalization', json={
        'task_kind': 'reply',
        'captured_context': {
            'active_app': 'Mail',
            'browser_url': 'https://mail.example.com/thread',
            'target_fingerprint': {'browser_domain': 'mail.example.com'},
        }
    })
    assert personalization.status_code == 200
    assert personalization.json()['style_profile']['tone_preference']['value'] == 'polished'

    suggestions = client.post('/assist/suggestions', json={
        'task_kind': 'reply',
        'captured_context': {
            'active_app': 'Mail',
            'browser_url': 'https://mail.example.com/thread',
            'input_text': 'Please send an update.',
            'target_fingerprint': {'browser_domain': 'mail.example.com'},
        }
    })
    assert suggestions.status_code == 200
    body = suggestions.json()
    assert body['suggestions']
    assert body['suggestions'][0]['command'] == 'Draft a reply to this'


def test_proactive_suggestions_endpoint(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)

    response = client.get('/proactive/suggestions')

    assert response.status_code == 200
    body = response.json()
    assert 'suggestions' in body
    assert 'captured_context' in body
    assert 'profile' in body


def test_run_state_exposes_hero_timing_metadata(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)

    run = client.post('/command', json={'text': 'Draft a reply to this', 'proactive': {'hero_timing': {'overlay_invoked_at': 1710800000000, 'overlay_visible_at': 1710800000080, 'overlay_submitted_at': 1710800000200}}})
    body = run.json()

    hero = body['run_state']['hero_timing']
    assert hero['marks']['overlay_visible_at'] is not None
    assert hero['durations_ms']['hotkey_to_overlay_visible'] == 80
    assert hero['phase'] == 'awaiting_approval'


def test_demo_status_endpoint_lists_scenarios(monkeypatch):
    monkeypatch.setenv('AURA_DEMO_MODE', '1')

    response = client.get('/demo/status')

    assert response.status_code == 200
    body = response.json()
    assert body['enabled'] is True
    assert {item['id'] for item in body['scenarios']} >= {'email_reply', 'research_answer', 'rewrite'}


def test_demo_start_uses_fixture_context_when_capture_is_unavailable(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)
    from aura import assist

    monkeypatch.setattr(assist, 'capture_context', lambda: {'ok': False, 'error': 'selection_missing', 'input_text': '', 'warnings': ['copy_or_select_text_first']})

    response = client.post('/demo/start', json={'scenario_id': 'email_reply'})
    body = response.json()

    assert response.status_code == 200
    assert body['status'] == 'awaiting_approval'
    assert body['run_state']['captured_context']['capture_path_used'] == 'demo_fixture'
    assert body['run_state']['demo']['used_fixture_context'] is True


def test_demo_start_uses_copy_fallback_when_paste_is_risky(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)
    from aura import assist

    monkeypatch.setattr(assist, 'restore_target_and_paste', lambda text, target, strict=False, cautious=False: failure('OS_PASTE', error='paste_target_changed', observation={'failure_class': 'paste_target_changed', 'target_validation_result': 'drifted', 'paste_attempted': False, 'paste_blocked_reason': 'target_drift_detected', 'context_drift_reason': 'browser_domain_changed'}, requires_user=True, retryable=True, result={'pasted': 0}))

    run = client.post('/demo/start', json={'scenario_id': 'email_reply'}).json()
    approved = client.post(f"/runs/{run['run_id']}/approve", json={'text': 'Approved API draft'})

    assert approved.status_code == 200
    assert approved.json()['ok'] is True
    state = client.get(f"/runs/{run['run_id']}").json()
    assert state['pasteback_state']['status'] == 'copied'
    assert state['pasteback_state']['demo_copy_fallback'] is True
    assert state['demo']['used_copy_fallback'] is True
