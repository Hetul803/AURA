from __future__ import annotations

from aura.learning import list_reflection_records, list_workflow_memory
from aura.orchestrator import approve_assist_run, reject_assist_run, retry_assist_run, run_command
from aura.planner import plan_from_text
from aura.prefs import reset_all, set_pref
from aura.state import db_conn
from storage.db import init_db
from tools.os_automation import capture_context as os_capture_context
from tools.tool_result import failure, success


def _clear_learning_tables():
    init_db()
    reset_all()
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


def test_context_capture_falls_back_to_clipboard(monkeypatch):
    from tools import os_automation

    monkeypatch.setattr(os_automation, 'get_active_app', lambda: success('OS_GET_ACTIVE_CONTEXT', result={'active_app': 'Notes'}, observation={'active_app': 'Notes'}))
    monkeypatch.setattr(os_automation, 'get_active_window_title', lambda: success('OS_GET_ACTIVE_CONTEXT', result={'window_title': 'Draft'}, observation={'window_title': 'Draft'}))
    monkeypatch.setattr(os_automation, 'get_browser_context', lambda _app=None: {})
    monkeypatch.setattr(os_automation, 'copy_selected_text', lambda: failure('OS_COPY_SELECTION', error='selection_unavailable', observation={}))
    monkeypatch.setattr(os_automation, 'read_clipboard', lambda: success('OS_READ_CLIPBOARD', result={'text': 'Clipboard fallback text', 'length': 23}, observation={'clipboard_length': 23}))

    captured = os_capture_context()

    assert captured['input_source'] == 'clipboard'
    assert captured['input_text'] == 'Clipboard fallback text'
    assert captured['capture_method']['clipboard_fallback_used'] is True


def test_planner_produces_assisted_writing_plan():
    plan = plan_from_text('Research this and answer')
    assert plan['signature'] == 'assist:writing'
    assert plan['assist']['task_kind'] == 'answer'
    assert plan['assist']['research_mode'] == 'web_search'
    assert plan['context']['approval_required'] is True


def _patch_assist(monkeypatch, *, input_text='Original source text. It has two useful details.', search_points=None, paste_result=None):
    from aura import assist

    monkeypatch.setattr(assist, 'capture_context', lambda: {
        'ok': True,
        'active_app': 'Notes',
        'window_title': 'Draft Window',
        'browser_url': 'https://example.com/page',
        'browser_title': 'Example Page',
        'selected_text': input_text,
        'clipboard_text': '',
        'input_text': input_text,
        'input_source': 'selected_text',
        'capture_method': {'selected_text_attempted': True, 'selected_text_succeeded': True, 'clipboard_fallback_used': False},
        'paste_target': {'app_name': 'Notes', 'window_title': 'Draft Window', 'target_url': 'https://example.com/page', 'captured_at': '2026-03-18T00:00:00Z'},
        'warnings': [],
    })
    monkeypatch.setattr(assist, 'handle_web_action', lambda step: success('WEB_READ', result={
        'key_points': search_points or ['Research note one.', 'Research note two.'],
        'sources': ['https://example.com/page', 'https://example.com/source'],
        'search_results_count': 2,
    }, observation={'search_results_count': 2}))
    calls = {'pastes': []}

    def fake_restore(text: str, target: dict):
        calls['pastes'].append((text, target))
        return paste_result or success('OS_PASTE', result={'pasted': len(text)}, observation={'target_validation': 'target_valid'})

    monkeypatch.setattr(assist, 'restore_target_and_paste', fake_restore)
    return calls


def test_first_run_gates_paste_until_approval(monkeypatch):
    _clear_learning_tables()
    calls = _patch_assist(monkeypatch)

    result = run_command('Summarize this')

    assert not result['ok']
    assert result['status'] == 'awaiting_approval'
    assert result['run_state']['approval_state']['status'] == 'pending'
    assert result['run_state']['draft_state']['draft_text']
    assert calls['pastes'] == []


def test_retry_regenerates_draft(monkeypatch):
    _clear_learning_tables()
    _patch_assist(monkeypatch, input_text='First sentence. Second sentence gives more detail. Third sentence adds context.')
    run = run_command('Explain this')

    first_draft = run['run_state']['draft_state']['draft_text']
    retried = retry_assist_run(run['run_id'], 'more detail')
    second_draft = retried['run_state']['draft_state']['draft_text']

    assert retried['status'] == 'awaiting_approval'
    assert second_draft != first_draft
    assert 'Second sentence gives more detail.' in second_draft


def test_rejection_stops_safely_and_records_learning(monkeypatch):
    _clear_learning_tables()
    _patch_assist(monkeypatch)
    run = run_command('Rewrite this better')

    rejected = reject_assist_run(run['run_id'], 'too stiff')

    assert rejected['status'] == 'rejected'
    assert rejected['run_state']['pasteback_state']['status'] == 'skipped'
    reflections = list_reflection_records(limit=1)
    assert reflections[0]['outcome'] == 'rejected'
    assert any(item['pattern_key'] == 'approval:rejected' for item in reflections[0]['candidate_workflow_patterns'])


def test_preference_influences_subsequent_draft(monkeypatch):
    _clear_learning_tables()
    set_pref('writing.length', 'detailed')
    set_pref('writing.tone', 'direct')
    _patch_assist(monkeypatch, input_text='Sentence one. Sentence two. Sentence three.')

    run = run_command('Summarize this')
    draft = run['run_state']['draft_state']['draft_text']

    assert 'Here’s a clear summary:' in draft
    assert 'Sentence two.' in draft
    assert run['run_state']['draft_state']['style_hints']['length'] == 'detailed'


def test_learning_captures_approval_and_workflow_success(monkeypatch):
    _clear_learning_tables()
    _patch_assist(monkeypatch)
    first = run_command('Draft a reply to this')
    approved = approve_assist_run(first['run_id'], 'Approved reply text.')

    assert approved['ok']
    reflections = list_reflection_records(limit=1)
    assert reflections[0]['normalized_context']['approval_status'] == 'pasted'
    workflow = list_workflow_memory()
    assert any(row['task_type'] == 'assist:writing' for row in workflow)


def test_safe_failure_when_target_context_is_lost(monkeypatch):
    _clear_learning_tables()
    paste_failure = failure('OS_PASTE', error='paste_target_changed', observation={'failure_class': 'paste_target_changed', 'failure_detail': 'window_title_changed'}, requires_user=True, retryable=True, result={'pasted': 0})
    _patch_assist(monkeypatch, paste_result=paste_failure)

    run = run_command('Summarize this')
    resumed = approve_assist_run(run['run_id'], 'Approved draft')

    assert not resumed['ok']
    assert resumed['status'] == 'needs_user'
    assert resumed['run_state']['last_failure_class'] == 'paste_target_changed'
