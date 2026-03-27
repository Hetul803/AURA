from __future__ import annotations

from types import SimpleNamespace

from aura.assist import classify_assist_task
from aura.learning import list_reflection_records
from aura.orchestrator import approve_assist_run, reject_assist_run, retry_assist_run, run_command
from aura.planner import plan_from_text
from aura.prefs import get_pref_value, reset_all
from aura.state import db_conn
from storage.db import init_db
from tools.os_automation import capture_context as os_capture_context
from tools.os_automation import copy_selected_text, restore_target_and_paste
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


def _intent(task_kind: str, *, needs_research: bool = False, confidence: float = 0.86):
    return SimpleNamespace(
        task_kind=task_kind,
        source_text_present=True,
        intent_confidence=confidence,
        needs_research=needs_research,
        style_hints={'tone': 'polished', 'length': 'concise'},
        approval_required=True,
        pasteback_mode='reactivate_validate_paste',
        reasoning_summary='mocked',
        provider='ollama',
        model='qwen2.5:3b',
        fallback_used=False,
    )


def _patch_assist(monkeypatch, *, task_kind='summarize', input_text='Original source text. It has two useful details.', search_points=None, paste_result=None):
    from aura import assist

    generate_calls = []
    search_calls = []

    monkeypatch.setattr(assist, 'classify_assist_request', lambda text: _intent(task_kind, needs_research=task_kind == 'research_and_respond'))
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
        'capture_path_used': 'selected_text',
        'capture_method': {'selection_copy_attempted': True, 'selection_copy_succeeded': True, 'clipboard_fallback_used': False, 'clipboard_preserved': True, 'clipboard_restored_after_capture': True, 'capture_failure_reason': None},
        'target_fingerprint': {'app_name': 'Notes', 'window_title': 'Draft Window', 'browser_url': 'https://example.com/page', 'browser_domain': 'example.com', 'browser_title': 'Example Page', 'captured_at': '2026-03-18T00:00:00Z', 'capture_path_used': 'selected_text', 'normalized': {'app_name': 'notes', 'window_title': 'draft window', 'browser_url': 'https://example.com/page', 'browser_domain': 'example.com', 'browser_title': 'example page'}},
        'paste_target': {'app_name': 'Notes', 'window_title': 'Draft Window', 'browser_url': 'https://example.com/page', 'browser_domain': 'example.com', 'browser_title': 'Example Page', 'captured_at': '2026-03-18T00:00:00Z', 'capture_path_used': 'selected_text', 'normalized': {'app_name': 'notes', 'window_title': 'draft window', 'browser_url': 'https://example.com/page', 'browser_domain': 'example.com', 'browser_title': 'example page'}},
        'warnings': [],
    })

    def fake_search(step):
        search_calls.append(step.args['query'])
        return success('WEB_READ', result={
            'key_points': search_points or ['Research note one.', 'Research note two.'],
            'sources': ['https://example.com/page', 'https://example.com/source'],
            'search_results_count': 2,
        }, observation={'search_results_count': 2})

    monkeypatch.setattr(assist, 'handle_web_action', fake_search)

    def fake_generate(**kwargs):
        generate_calls.append(kwargs)
        tone = kwargs['style_hints'].get('tone', 'polished')
        length = kwargs['style_hints'].get('length', 'concise')
        research = kwargs['research_context']
        source = kwargs['source_text']
        draft = f"[{tone}/{length}] {kwargs['task_kind']} -> {source}"
        if research.get('search_used'):
            draft += ' + research'
        if kwargs.get('retry_feedback'):
            draft += f" ({kwargs['retry_feedback']})"
        return SimpleNamespace(
            draft_text=draft,
            style_signals_used=dict(kwargs['style_hints']),
            research_used=bool(research.get('search_used')),
            provider='ollama',
            model='qwen2.5:3b',
            fallback_used=False,
            confidence=0.84,
            notes=['mocked_provider'],
        )

    monkeypatch.setattr(assist, 'generate_assist_draft', fake_generate)
    calls = {'pastes': [], 'generate_calls': generate_calls, 'search_calls': search_calls}

    def fake_restore(text: str, target: dict, strict: bool = False, cautious: bool = False):
        calls['pastes'].append((text, target, strict, cautious))
        return paste_result or success('OS_PASTE', result={'pasted': len(text)}, observation={'target_validation': 'exact_match', 'target_validation_result': 'exact_match', 'strict_validation': strict, 'cautious_validation': cautious, 'paste_attempted': True, 'clipboard_preserved': True, 'clipboard_restored_after_paste': True, 'paste_blocked_reason': None, 'context_drift_reason': None, 'target_fingerprint': target})

    monkeypatch.setattr(assist, 'restore_target_and_paste', fake_restore)
    return calls


def test_intent_classification_supports_all_assist_task_kinds():
    assert classify_assist_task('Summarize this')['task_kind'] == 'summarize'
    assert classify_assist_task('Draft a reply to this')['task_kind'] == 'reply'
    assert classify_assist_task('Rewrite this better')['task_kind'] == 'rewrite'
    assert classify_assist_task('Explain this')['task_kind'] == 'explain'
    assert classify_assist_task('Answer this question')['task_kind'] == 'answer'
    assert classify_assist_task('Research this and respond')['task_kind'] == 'research_and_respond'


def test_context_capture_falls_back_to_clipboard(monkeypatch):
    from tools import os_automation

    monkeypatch.setattr(os_automation, 'get_active_app', lambda: success('OS_GET_ACTIVE_CONTEXT', result={'active_app': 'Notes'}, observation={'active_app': 'Notes'}))
    monkeypatch.setattr(os_automation, 'get_active_window_title', lambda: success('OS_GET_ACTIVE_CONTEXT', result={'window_title': 'Draft'}, observation={'window_title': 'Draft'}))
    monkeypatch.setattr(os_automation, 'get_browser_context', lambda _app=None: {})
    monkeypatch.setattr(os_automation, 'copy_selected_text', lambda: failure('OS_COPY_SELECTION', error='selection_unavailable', observation={'selection_copy_attempted': True, 'selection_copy_succeeded': False, 'clipboard_preserved': True, 'clipboard_restored_after_capture': True, 'capture_failure_reason': 'selection_copy_no_change'}, result={'original_clipboard_text': 'Clipboard fallback text', 'clipboard_preserved': True, 'clipboard_restored_after_capture': True}))

    captured = os_capture_context()

    assert captured['input_source'] == 'clipboard_fallback'
    assert captured['input_text'] == 'Clipboard fallback text'
    assert captured['capture_path_used'] == 'clipboard_fallback'
    assert captured['capture_method']['clipboard_fallback_used'] is True
    assert captured['capture_method']['clipboard_restored_after_capture'] is True


def test_context_capture_reports_none_when_no_usable_source(monkeypatch):
    from tools import os_automation

    monkeypatch.setattr(os_automation, 'get_active_app', lambda: success('OS_GET_ACTIVE_CONTEXT', result={'active_app': 'Notes'}, observation={'active_app': 'Notes'}))
    monkeypatch.setattr(os_automation, 'get_active_window_title', lambda: success('OS_GET_ACTIVE_CONTEXT', result={'window_title': 'Draft'}, observation={'window_title': 'Draft'}))
    monkeypatch.setattr(os_automation, 'get_browser_context', lambda _app=None: {})
    monkeypatch.setattr(os_automation, 'copy_selected_text', lambda: failure('OS_COPY_SELECTION', error='selection_unavailable', observation={'selection_copy_attempted': True, 'selection_copy_succeeded': False, 'clipboard_preserved': True, 'clipboard_restored_after_capture': True, 'capture_failure_reason': 'selection_copy_no_change'}, result={'original_clipboard_text': '', 'clipboard_preserved': True, 'clipboard_restored_after_capture': True}))

    captured = os_capture_context()

    assert captured['capture_path_used'] == 'none'
    assert captured['input_text'] == ''
    assert 'copy_or_select_text_first' in captured['warnings']


def test_context_capture_records_selection_clipboard_safety(monkeypatch):
    from tools import os_automation

    monkeypatch.setattr(os_automation, 'get_active_app', lambda: success('OS_GET_ACTIVE_CONTEXT', result={'active_app': 'Mail'}, observation={'active_app': 'Mail'}))
    monkeypatch.setattr(os_automation, 'get_active_window_title', lambda: success('OS_GET_ACTIVE_CONTEXT', result={'window_title': 'Composer'}, observation={'window_title': 'Composer'}))
    monkeypatch.setattr(os_automation, 'get_browser_context', lambda _app=None: {'browser_url': 'https://mail.example.com/thread', 'browser_title': 'Mail Thread'})
    monkeypatch.setattr(os_automation, 'copy_selected_text', lambda: success('OS_COPY_SELECTION', result={'text': 'Selected text', 'original_clipboard_text': 'Original clipboard', 'clipboard_preserved': True, 'clipboard_restored_after_capture': True, 'clipboard_restore_error_after_capture': None}, observation={'selection_copy_attempted': True, 'selection_copy_succeeded': True, 'clipboard_preserved': True, 'clipboard_restored_after_capture': True}))

    captured = os_capture_context()

    assert captured['capture_path_used'] == 'selected_text'
    assert captured['capture_method']['clipboard_preserved'] is True
    assert captured['capture_method']['clipboard_restored_after_capture'] is True
    assert captured['target_fingerprint']['browser_domain'] == 'mail.example.com'


def test_selection_copy_preserves_and_restores_clipboard(monkeypatch):
    from tools import os_automation

    clipboard_reads = iter(['Original clipboard', 'Selected text'])
    restore_calls = []

    monkeypatch.setattr(os_automation, 'SYSTEM', 'darwin')
    monkeypatch.setattr(os_automation, '_preserve_clipboard', lambda: {'ok': True, 'preserved': True, 'text': 'Original clipboard', 'length': 18, 'error': None})
    monkeypatch.setattr(os_automation, 'press_keys', lambda keys: success('OS_PRESS_KEYS', result={'keys': keys}, observation={}))
    monkeypatch.setattr(os_automation, '_clipboard_text', lambda: next(clipboard_reads))
    monkeypatch.setattr(os_automation, '_restore_clipboard_text', lambda text, reason: restore_calls.append((text, reason)) or {'ok': True, 'restored': True, 'error': None, 'reason': reason})

    copied = copy_selected_text()

    assert copied['ok'] is True
    assert copied['result']['text'] == 'Selected text'
    assert copied['result']['clipboard_preserved'] is True
    assert copied['result']['clipboard_restored_after_capture'] is True
    assert restore_calls == [('Original clipboard', 'after_capture')]


def test_planner_produces_richer_assisted_writing_plan(monkeypatch):
    from aura import assist

    monkeypatch.setattr(assist, 'classify_assist_request', lambda text: _intent('research_and_respond', needs_research=True, confidence=0.91))
    plan = plan_from_text('Research this and respond')
    assert plan['signature'] == 'assist:writing'
    assert plan['assist']['task_kind'] == 'research_and_respond'
    assert plan['assist']['intent_confidence'] == 0.91
    assert plan['assist']['classifier']['provider'] == 'ollama'
    assert plan['assist']['research_mode'] == 'web_search'


def test_drafting_uses_model_backed_provider(monkeypatch):
    _clear_learning_tables()
    calls = _patch_assist(monkeypatch)

    result = run_command('Summarize this')

    assert result['status'] == 'awaiting_approval'
    assert calls['generate_calls']
    assert result['run_state']['assist']['generation']['provider'] == 'ollama'
    assert result['run_state']['draft_state']['provider'] == 'ollama'


def test_explicit_failure_if_no_real_model_is_available(monkeypatch):
    _clear_learning_tables()
    from aura import assist

    monkeypatch.setattr(assist, 'classify_assist_request', lambda text: _intent('summarize'))
    monkeypatch.setattr(assist, 'capture_context', lambda: {
        'ok': True,
        'active_app': 'Notes',
        'window_title': 'Draft Window',
        'browser_url': None,
        'browser_title': None,
        'selected_text': 'Source',
        'clipboard_text': '',
        'input_text': 'Source',
        'input_source': 'selected_text',
        'capture_path_used': 'selected_text',
        'capture_method': {'selection_copy_attempted': True, 'selection_copy_succeeded': True, 'clipboard_fallback_used': False, 'clipboard_preserved': True, 'clipboard_restored_after_capture': True, 'capture_failure_reason': None},
        'target_fingerprint': {'app_name': 'Notes', 'window_title': 'Draft Window', 'captured_at': '2026-03-18T00:00:00Z', 'capture_path_used': 'selected_text', 'normalized': {'app_name': 'notes', 'window_title': 'draft window'}},
        'paste_target': {'app_name': 'Notes', 'window_title': 'Draft Window', 'captured_at': '2026-03-18T00:00:00Z', 'capture_path_used': 'selected_text', 'normalized': {'app_name': 'notes', 'window_title': 'draft window'}},
        'warnings': [],
    })
    monkeypatch.setattr(assist, 'generate_assist_draft', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('assist_model_unavailable')))

    run = run_command('Summarize this')

    assert not run['ok']
    assert run['status'] == 'needs_user'
    assert run['run_state']['last_failure_class'] == 'assist_model_unavailable'


def test_bounded_research_runs_when_appropriate(monkeypatch):
    _clear_learning_tables()
    calls = _patch_assist(monkeypatch, task_kind='research_and_respond')

    run = run_command('Research this and respond')

    assert run['status'] == 'awaiting_approval'
    assert len(calls['search_calls']) == 1
    assert run['run_state']['research_context']['search_used'] is True
    assert run['run_state']['draft_state']['research_used'] is True


def test_approval_gates_paste_until_explicit_approval(monkeypatch):
    _clear_learning_tables()
    calls = _patch_assist(monkeypatch)

    result = run_command('Summarize this')

    assert not result['ok']
    assert result['status'] == 'awaiting_approval'
    assert result['run_state']['approval_state']['status'] == 'pending'
    assert calls['pastes'] == []


def test_retry_regenerate_updates_future_style_preference(monkeypatch):
    _clear_learning_tables()
    calls = _patch_assist(monkeypatch, task_kind='explain', input_text='First sentence. Second sentence gives more detail. Third sentence adds context.')
    run = run_command('Explain this')

    retried = retry_assist_run(run['run_id'], 'more direct and more detail')

    assert retried['status'] == 'awaiting_approval'
    assert get_pref_value('writing.tone') == 'direct'
    assert get_pref_value('writing.length') == 'detailed'
    assert '[direct/detailed]' in retried['run_state']['draft_state']['draft_text']
    assert len(calls['generate_calls']) >= 2


def test_rejection_stops_safely(monkeypatch):
    _clear_learning_tables()
    _patch_assist(monkeypatch, task_kind='rewrite')
    run = run_command('Rewrite this better')

    rejected = reject_assist_run(run['run_id'], 'not needed, no research')

    assert rejected['status'] == 'rejected'
    assert rejected['run_state']['pasteback_state']['status'] == 'skipped'


def test_successful_paste_back_path_records_provider_and_validation(monkeypatch):
    _clear_learning_tables()
    calls = _patch_assist(monkeypatch)
    run = run_command('Draft a reply to this')
    approved = approve_assist_run(run['run_id'], 'Approved reply text.')

    assert approved['ok']
    assert calls['pastes']
    assert approved['run_state']['pasteback_state']['status'] == 'pasted'
    assert approved['run_state']['assist']['paste_validation']['target_validation_result'] == 'exact_match'
    assert approved['run_state']['pasteback_state']['clipboard_restored_after_paste'] is True
    assert approved['run_state']['assist']['generation']['provider'] == 'ollama'


def test_safe_stop_when_context_is_lost(monkeypatch):
    _clear_learning_tables()
    paste_failure = failure('OS_PASTE', error='paste_target_changed', observation={'failure_class': 'paste_target_changed', 'failure_detail': 'window_title_changed', 'strict_validation': True, 'target_validation_result': 'drifted', 'target_validation': 'active_app_changed', 'paste_attempted': False, 'paste_blocked_reason': 'target_drift_detected', 'context_drift_reason': 'window_title_changed', 'clipboard_restored_after_paste': True}, requires_user=True, retryable=True, result={'pasted': 0})
    _patch_assist(monkeypatch, paste_result=paste_failure)

    run = run_command('Summarize this')
    resumed = approve_assist_run(run['run_id'], 'Approved draft')

    assert not resumed['ok']
    assert resumed['status'] == 'needs_user'
    assert resumed['run_state']['last_failure_class'] == 'paste_target_changed'
    assert resumed['run_state']['pasteback_state']['target_validation_result'] == 'drifted'
    assert resumed['run_state']['pasteback_state']['paste_blocked_reason'] == 'target_drift_detected'


def test_target_fingerprint_is_stored_in_run_state(monkeypatch):
    _clear_learning_tables()
    calls = _patch_assist(monkeypatch)
    run = run_command('Summarize this')

    assert calls['generate_calls']
    assert run['run_state']['captured_context']['target_fingerprint']['app_name'] == 'Notes'
    assert run['run_state']['assist']['target_fingerprint']['browser_domain'] == 'example.com'


def test_restore_target_and_paste_allows_exact_and_acceptable_matches(monkeypatch):
    from tools import os_automation

    target = {
        'app_name': 'Notes',
        'window_title': 'Draft Window',
        'browser_url': 'https://example.com/page',
        'browser_domain': 'example.com',
        'browser_title': 'Example Page',
        'normalized': {
            'app_name': 'notes',
            'window_title': 'draft window',
            'browser_url': 'https://example.com/page',
            'browser_domain': 'example.com',
            'browser_title': 'example page',
        },
    }
    monkeypatch.setattr(os_automation, 'activate_app', lambda app_name: success('OS_ACTIVATE_APP', result={'app': app_name}, observation={}))
    monkeypatch.setattr(os_automation, 'active_context', lambda: {'active_app': 'Notes', 'window_title': 'Draft Window – follow-up', 'browser_url': 'https://example.com/other', 'browser_title': 'Example Page – follow-up', 'normalized': {'active_app': 'notes', 'window_title': 'draft window – follow-up', 'browser_url': 'https://example.com/other', 'browser_domain': 'example.com', 'browser_title': 'example page – follow-up'}})
    monkeypatch.setattr(os_automation, 'paste_to_active_app', lambda text, preserve_clipboard=True: success('OS_PASTE', result={'pasted': len(text)}, observation={'clipboard_preserved': True, 'clipboard_restored_after_paste': True}))

    pasted = restore_target_and_paste('Approved draft', target, strict=False, cautious=False)

    assert pasted['ok'] is True
    assert pasted['observation']['target_validation_result'] == 'acceptable_match'
    assert pasted['observation']['paste_attempted'] is True


def test_restore_target_and_paste_blocks_drifted_or_cautious_targets(monkeypatch):
    from tools import os_automation

    target = {
        'app_name': 'Notes',
        'window_title': 'Draft Window',
        'browser_url': 'https://example.com/page',
        'browser_domain': 'example.com',
        'browser_title': 'Example Page',
        'normalized': {
            'app_name': 'notes',
            'window_title': 'draft window',
            'browser_url': 'https://example.com/page',
            'browser_domain': 'example.com',
            'browser_title': 'example page',
        },
    }
    monkeypatch.setattr(os_automation, 'activate_app', lambda app_name: success('OS_ACTIVATE_APP', result={'app': app_name}, observation={}))
    monkeypatch.setattr(os_automation, 'paste_to_active_app', lambda text, preserve_clipboard=True: success('OS_PASTE', result={'pasted': len(text)}, observation={}))

    monkeypatch.setattr(os_automation, 'active_context', lambda: {'active_app': 'Mail', 'window_title': 'Inbox', 'browser_url': 'https://mail.example.com', 'browser_title': 'Inbox', 'normalized': {'active_app': 'mail', 'window_title': 'inbox', 'browser_url': 'https://mail.example.com', 'browser_domain': 'mail.example.com', 'browser_title': 'inbox'}})
    drifted = restore_target_and_paste('Approved draft', target, strict=False, cautious=False)
    assert drifted['ok'] is False
    assert drifted['observation']['target_validation_result'] == 'drifted'
    assert drifted['observation']['paste_blocked_reason'] == 'target_drift_detected'

    monkeypatch.setattr(os_automation, 'active_context', lambda: {'active_app': 'Notes', 'window_title': 'Draft Window – follow-up', 'browser_url': 'https://example.com/other', 'browser_title': 'Example Page – follow-up', 'normalized': {'active_app': 'notes', 'window_title': 'draft window – follow-up', 'browser_url': 'https://example.com/other', 'browser_domain': 'example.com', 'browser_title': 'example page – follow-up'}})
    cautious = restore_target_and_paste('Approved draft', target, strict=False, cautious=True)
    assert cautious['ok'] is False
    assert cautious['observation']['target_validation_result'] == 'acceptable_match'
    assert cautious['observation']['paste_blocked_reason'] == 'acceptable_match_requires_caution'


def test_acceptable_match_paste_back_is_allowed_without_caution(monkeypatch):
    _clear_learning_tables()
    paste_result = success('OS_PASTE', result={'pasted': 19}, observation={'target_validation': 'acceptable_match', 'target_validation_result': 'acceptable_match', 'strict_validation': False, 'cautious_validation': False, 'paste_attempted': True, 'clipboard_preserved': True, 'clipboard_restored_after_paste': True, 'paste_blocked_reason': None, 'context_drift_reason': None})
    calls = _patch_assist(monkeypatch, paste_result=paste_result)

    run = run_command('Summarize this')
    approved = approve_assist_run(run['run_id'], 'Approved draft text')

    assert approved['ok']
    assert calls['pastes']
    assert approved['run_state']['pasteback_state']['target_validation_result'] == 'acceptable_match'


def test_repeated_drift_influences_future_caution(monkeypatch):
    _clear_learning_tables()
    drift_failure = failure('OS_PASTE', error='paste_target_changed', observation={'failure_class': 'paste_target_changed', 'failure_detail': 'browser_domain_changed', 'strict_validation': True, 'target_validation_result': 'drifted', 'target_validation': 'active_app_changed', 'paste_attempted': False, 'paste_blocked_reason': 'target_drift_detected', 'context_drift_reason': 'browser_domain_changed', 'clipboard_restored_after_paste': True}, requires_user=True, retryable=True, result={'pasted': 0})
    _patch_assist(monkeypatch, paste_result=drift_failure)

    first = run_command('Summarize this')
    approve_assist_run(first['run_id'], 'Approved draft')

    _patch_assist(monkeypatch)
    second = run_command('Summarize this')

    assert second['run_state']['draft_state']['learning_signals_applied']['strict_paste_validation'] is True
    assert second['run_state']['draft_state']['learning_signals_applied']['cautious_paste_mode'] is True


def test_learning_influences_later_runs(monkeypatch):
    _clear_learning_tables()
    _patch_assist(monkeypatch, task_kind='summarize')
    first = run_command('Summarize this')
    retry_assist_run(first['run_id'], 'more direct and more detail')

    second = run_command('Summarize this')

    assert '[direct/detailed]' in second['run_state']['draft_state']['draft_text']
    reflections = list_reflection_records(limit=3)
    assert reflections
