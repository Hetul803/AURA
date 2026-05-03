from __future__ import annotations

from types import SimpleNamespace

from aura.learning import list_workflow_memory
from aura.orchestrator import approve_assist_run, reject_assist_run, run_command
from aura.proactive import proactive_suggestions_for_context
from aura.state import db_conn
from storage.db import init_db


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
        task_kind='reply',
        source_text_present=True,
        intent_confidence=0.9,
        needs_research=False,
        style_hints={'tone': 'polished', 'length': 'concise'},
        approval_required=True,
        pasteback_mode='reactivate_validate_paste',
        reasoning_summary='mocked',
        provider='ollama',
        model='qwen2.5:3b',
        fallback_used=False,
    ))
    monkeypatch.setattr(assist, 'capture_context', lambda: {
        'ok': True,
        'active_app': 'Mail',
        'window_title': 'Inbox',
        'browser_url': 'https://mail.example.com/thread',
        'browser_title': 'Thread',
        'selected_text': 'Hi team,\nCan you send the updated rollout timeline?\nThanks,',
        'clipboard_text': '',
        'input_text': 'Hi team,\nCan you send the updated rollout timeline?\nThanks,',
        'input_source': 'selected_text',
        'capture_path_used': 'selected_text',
        'capture_method': {'selection_copy_attempted': True, 'selection_copy_succeeded': True, 'clipboard_fallback_used': False, 'clipboard_preserved': True, 'clipboard_restored_after_capture': True, 'capture_failure_reason': None},
        'target_fingerprint': {'app_name': 'Mail', 'browser_domain': 'mail.example.com', 'browser_url': 'https://mail.example.com/thread', 'normalized': {'app_name': 'mail', 'browser_domain': 'mail.example.com'}},
        'paste_target': {'app_name': 'Mail', 'browser_domain': 'mail.example.com', 'browser_url': 'https://mail.example.com/thread', 'normalized': {'app_name': 'mail', 'browser_domain': 'mail.example.com'}},
        'warnings': [],
    })
    monkeypatch.setattr(assist, 'generate_assist_draft', lambda **kwargs: SimpleNamespace(
        draft_text='Draft reply',
        style_signals_used=dict(kwargs['style_hints']),
        research_used=False,
        provider='ollama',
        model='qwen2.5:3b',
        fallback_used=False,
        confidence=0.86,
        notes=['mocked_provider'],
    ))
    monkeypatch.setattr(assist, 'restore_target_and_paste', lambda text, target, strict=False, cautious=False: {
        'ok': True,
        'action': 'ASSIST_PASTE_BACK',
        'result': {'pasted': len(text)},
        'observation': {'target_validation_result': 'exact_match', 'target_validation': 'exact_match', 'strict_validation': strict, 'cautious_validation': cautious, 'paste_attempted': True, 'target_fingerprint': target},
    })


def test_proactive_engine_prefers_reply_in_mail_context():
    _clear_tables()

    result = proactive_suggestions_for_context({
        'active_app': 'Mail',
        'browser_url': 'https://mail.example.com/thread',
        'input_text': 'Hi team,\nCan you send the updated rollout timeline?\nThanks,',
        'target_fingerprint': {'browser_domain': 'mail.example.com'},
    })

    assert result['suggestions']
    assert len(result['suggestions']) <= 3
    assert result['suggestions'][0]['action'] == 'reply'
    assert result['suggestions'][0]['confidence'] >= 0.58
    assert result['suggestions'][0]['signals_used']


def test_proactive_engine_suppresses_low_confidence_suggestions():
    _clear_tables()

    result = proactive_suggestions_for_context({
        'active_app': 'Finder',
        'window_title': 'Empty',
        'input_text': 'Okay.',
    })

    assert result['suggestions'] == []


def test_proactive_feedback_records_selection_and_rejection(monkeypatch):
    _clear_tables()
    _patch_assist(monkeypatch)
    proactive = {
        'suggestions_shown': [{'action': 'reply', 'confidence': 0.84}],
        'suggestion_selected': 'reply',
        'suggestion_confidence': 0.84,
        'signals_used': [{'name': 'mail_surface', 'weight': 0.28}],
    }

    run = run_command('Draft a reply to this', proactive=proactive)
    approve_assist_run(run['run_id'], 'Approved proactive draft')

    success_patterns = [row for row in list_workflow_memory() if row['pattern_key'] == 'proactive:reply:selected']
    assert success_patterns
    assert success_patterns[0]['success_count'] >= 1

    rejected_run = run_command('Draft a reply to this', proactive=proactive)
    reject_assist_run(rejected_run['run_id'], 'not needed')

    rejection_patterns = [row for row in list_workflow_memory() if row['pattern_key'] == 'proactive:reply:rejected']
    assert rejection_patterns
    assert rejection_patterns[0]['failure_count'] >= 1


def test_rejection_history_weakens_proactive_confidence():
    _clear_tables()
    context = {
        'active_app': 'Mail',
        'browser_url': 'https://mail.example.com/thread',
        'input_text': 'Hi team,\nCan you send the updated rollout timeline?\nThanks,',
        'target_fingerprint': {'browser_domain': 'mail.example.com'},
    }
    baseline = proactive_suggestions_for_context(context)
    baseline_reply = next(item for item in baseline['suggestions'] if item['action'] == 'reply')

    with db_conn() as conn:
        conn.execute(
            "INSERT INTO workflow_memory(task_type, pattern_key, strategy, confidence, success_count, failure_count, last_seen, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ('assist:writing', 'proactive:reply:rejected', 'overlay_proactive_suggestion', 0.8, 0, 3, '2026-03-19T00:00:00Z', ''),
        )

    weakened = proactive_suggestions_for_context(context)
    weakened_reply = next(item for item in weakened['suggestions'] if item['action'] == 'reply')

    assert weakened_reply['confidence'] < baseline_reply['confidence']
