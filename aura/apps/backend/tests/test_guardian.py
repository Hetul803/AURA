from __future__ import annotations

from types import SimpleNamespace

from aura.guardian import events_for_step, record_step_events
from aura.state import list_guardian_events, set_run_context


def _step(action_type: str, **args):
    return SimpleNamespace(id=f'{action_type.lower()}-1', action_type=action_type, args=args)


def test_guardian_classifies_clipboard_capture_and_large_paste():
    run_id = 'guardian-clipboard'
    set_run_context(run_id, {'guardian_events': [], 'captured_context': {'active_app': 'Mail', 'target_fingerprint': {'browser_domain': 'mail.example.com'}}})

    capture = events_for_step(run_id, _step('ASSIST_CAPTURE_CONTEXT'), {
        'result': {'captured_context': {'input_text': 'hello', 'capture_path_used': 'clipboard_fallback', 'capture_method': {'clipboard_preserved': True, 'clipboard_restored_after_capture': True}}},
        'observation': {},
    }, {})
    paste = events_for_step(run_id, _step('ASSIST_PASTE_BACK', text='x' * 2200), {
        'result': {'pasted': 2200},
        'observation': {'target_validation_result': 'exact_match', 'clipboard_preserved': True, 'clipboard_restored_after_paste': True},
    }, {'captured_context': {'active_app': 'Mail', 'target_fingerprint': {'browser_domain': 'mail.example.com'}}})

    assert capture[0]['type'] == 'clipboard_read'
    assert capture[0]['risk'] == 'medium'
    assert paste[0]['type'] == 'clipboard_write'
    assert paste[0]['risk'] == 'high'


def test_guardian_records_external_research_events_and_global_feed():
    run_id = 'guardian-network'
    set_run_context(run_id, {'guardian_events': []})
    step = _step('ASSIST_RESEARCH_CONTEXT', research_mode='web_search')
    result = {
        'result': {'research_context': {'search_used': True, 'query': 'aura assistant', 'sources': ['https://example.com'], 'search_results_count': 1}},
        'observation': {'research_used': True},
    }

    recorded = record_step_events(run_id, step, result, {})

    assert recorded[0]['type'] == 'network_action'
    assert recorded[0]['risk'] == 'high'
    assert list_guardian_events(run_id=run_id, limit=5)[0]['summary'].startswith('AURA performed an external research query')
