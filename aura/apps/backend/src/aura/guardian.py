from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from .state import append_run_history, get_run_context, list_guardian_events, record_guardian_event

LOW = 'low'
MEDIUM = 'medium'
HIGH = 'high'

CLIPBOARD_READ_ACTIONS = {'OS_READ_CLIPBOARD', 'OS_COPY_SELECTION', 'ASSIST_CAPTURE_CONTEXT'}
CLIPBOARD_WRITE_ACTIONS = {'OS_WRITE_CLIPBOARD', 'OS_PASTE', 'ASSIST_PASTE_BACK'}
FILE_ACTIONS = {'FS_EXISTS', 'FS_READ_TEXT', 'FS_WRITE_TEXT'}
BROWSER_ACTIONS = {'OS_OPEN_URL', 'WEB_NAVIGATE', 'WEB_READ', 'WEB_UPLOAD', 'ASSIST_RESEARCH_CONTEXT'}


def _domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return parsed.netloc or None


def _repetition_count(run_id: str, event_type: str, target: str | None = None) -> int:
    events = list_guardian_events(run_id=run_id, limit=100)
    count = 0
    for item in events:
        if item.get('type') != event_type:
            continue
        item_target = str((item.get('context') or {}).get('target') or '')
        if target and item_target and item_target != target:
            continue
        count += 1
    return count


def _size_hint(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    try:
        return int(value or 0)
    except Exception:
        return 0


def _base_event(*, run_id: str, step, event_type: str, risk: str, summary: str, explanation: str, context: dict | None = None) -> dict:
    return {
        'run_id': run_id,
        'step_id': getattr(step, 'id', None),
        'action': getattr(step, 'action_type', ''),
        'type': event_type,
        'source': 'AURA',
        'risk': risk,
        'summary': summary,
        'explanation': explanation,
        'context': context or {},
        'timestamp': time.time(),
    }


def _clipboard_event(run_id: str, step, result: dict, run_context: dict) -> list[dict]:
    observation = result.get('observation') or {}
    outcome = result.get('result') or {}
    action = step.action_type
    if action in {'OS_READ_CLIPBOARD', 'OS_COPY_SELECTION', 'ASSIST_CAPTURE_CONTEXT'}:
        event_type = 'clipboard_read'
        size = _size_hint(outcome.get('text') or outcome.get('length') or observation.get('clipboard_length') or ((outcome.get('captured_context') or {}).get('input_text')))
        capture = outcome.get('captured_context') or {}
        source = capture.get('capture_path_used') or outcome.get('capture_path_used') or observation.get('capture_path_used') or 'clipboard'
        summary = 'AURA read from the clipboard to capture context.' if action == 'ASSIST_CAPTURE_CONTEXT' else 'AURA accessed clipboard content.'
        explanation = 'This happened during context capture or selection copy so AURA could work with the active text.'
        risk = LOW
        if source == 'clipboard_fallback' or size >= 800:
            risk = MEDIUM
            summary = 'AURA used the clipboard fallback to capture context.'
            explanation = 'No reliable text selection was available, so AURA relied on clipboard contents from the active app.'
        if _repetition_count(run_id, event_type) >= 1:
            risk = MEDIUM
            explanation = 'AURA accessed clipboard content multiple times during this run.'
        context = {
            'target': source,
            'size': size,
            'clipboard_preserved': observation.get('clipboard_preserved', (capture.get('capture_method') or {}).get('clipboard_preserved')),
            'clipboard_restored': observation.get('clipboard_restored_after_capture', (capture.get('capture_method') or {}).get('clipboard_restored_after_capture')),
        }
        return [_base_event(run_id=run_id, step=step, event_type=event_type, risk=risk, summary=summary, explanation=explanation, context=context)]

    size = _size_hint(outcome.get('written') or outcome.get('pasted') or step.args.get('text') or observation.get('clipboard_length'))
    target = ((run_context.get('captured_context') or {}).get('target_fingerprint') or {}).get('browser_domain') or ((observation.get('target_fingerprint') or {}).get('browser_domain')) or (run_context.get('captured_context') or {}).get('active_app') or 'active_app'
    risk = LOW
    summary = 'AURA prepared clipboard content for paste-back.' if action == 'ASSIST_PASTE_BACK' else 'AURA wrote content to the clipboard.'
    explanation = 'This is part of AURA placing generated or requested text into the active app.'
    if size >= 600 or action in {'OS_PASTE', 'ASSIST_PASTE_BACK'}:
        risk = MEDIUM
        summary = 'AURA pasted or staged a larger block of content.'
        explanation = 'AURA placed a sizable result onto the clipboard and attempted paste-back into the active target.'
    if size >= 1800:
        risk = HIGH
        summary = 'AURA pasted a large block of content into another app.'
        explanation = 'Large paste-back actions can move substantial text into the active app, so AURA marks them as higher risk.'
    if _repetition_count(run_id, 'clipboard_write', str(target)) >= 1:
        risk = HIGH if risk in {MEDIUM, HIGH} else MEDIUM
        explanation = 'AURA interacted with the clipboard repeatedly for this target during the same run.'
    context = {
        'target': str(target),
        'size': size,
        'clipboard_preserved': observation.get('clipboard_preserved'),
        'clipboard_restored': observation.get('clipboard_restored_after_paste'),
        'target_validation_result': observation.get('target_validation_result') or observation.get('target_validation'),
    }
    return [_base_event(run_id=run_id, step=step, event_type='clipboard_write', risk=risk, summary=summary, explanation=explanation, context=context)]


def _file_event(run_id: str, step, result: dict) -> list[dict]:
    observation = result.get('observation') or {}
    path = observation.get('path') or step.args.get('path') or ''
    size = _size_hint((result.get('result') or {}).get('written') or observation.get('size'))
    operation = 'read' if step.action_type == 'FS_READ_TEXT' else 'write' if step.action_type == 'FS_WRITE_TEXT' else 'inspect'
    risk = LOW
    if operation == 'write' and size >= 2000:
        risk = MEDIUM
    summary = f"AURA {operation} a local file."
    explanation = 'This event is limited to filesystem actions AURA performed inside its own workflow.'
    context = {'target': path, 'operation': operation, 'size': size, 'file_exists': observation.get('file_exists')}
    return [_base_event(run_id=run_id, step=step, event_type='file_access', risk=risk, summary=summary, explanation=explanation, context=context)]


def _browser_events(run_id: str, step, result: dict, run_context: dict) -> list[dict]:
    observation = result.get('observation') or {}
    action = step.action_type
    events: list[dict] = []
    url = observation.get('url') or step.args.get('url')
    target = step.args.get('target') or _domain(url) or step.args.get('query') or 'browser'

    if action == 'ASSIST_RESEARCH_CONTEXT':
        research = (result.get('result') or {}).get('research_context') or {}
        if not research.get('search_used'):
            return []
        target = research.get('query') or (research.get('sources') or ['search'])[0]
        risk = HIGH
        summary = 'AURA performed an external research query.'
        explanation = 'The assist flow used a web search to gather outside context before drafting a response.'
        if _repetition_count(run_id, 'network_action') >= 1:
            explanation = 'AURA used external research multiple times during this run.'
        events.append(_base_event(
            run_id=run_id,
            step=step,
            event_type='network_action',
            risk=risk,
            summary=summary,
            explanation=explanation,
            context={'target': str(target), 'sources': list(research.get('sources') or [])[:3], 'search_results_count': research.get('search_results_count', 0)},
        ))
        return events

    risk = LOW
    summary = 'AURA accessed a browser context.'
    explanation = 'This reflects AURA visiting or reading from a page that it can observe in its workflow.'
    if action in {'WEB_READ', 'WEB_NAVIGATE', 'WEB_UPLOAD', 'OS_OPEN_URL'}:
        risk = MEDIUM
    if action in {'WEB_READ', 'WEB_UPLOAD'} and (step.args.get('target') == 'search' or _domain(url) not in {None, '', 'localhost', '127.0.0.1'}):
        risk = HIGH if action == 'WEB_UPLOAD' else MEDIUM
        summary = 'AURA reached an external web destination.'
        explanation = 'This browser action involved an external page or search target rather than only local context.'
    if action == 'WEB_UPLOAD':
        events.append(_base_event(
            run_id=run_id,
            step=step,
            event_type='network_action',
            risk=HIGH,
            summary='AURA prepared a browser upload action.',
            explanation='Uploading through a browser can move a local file into an external destination, so AURA flags it as high risk.',
            context={'target': step.args.get('url') or step.args.get('selector') or 'upload', 'file_path': step.args.get('file_path')},
        ))
    events.insert(0, _base_event(
        run_id=run_id,
        step=step,
        event_type='browser_access',
        risk=risk,
        summary=summary,
        explanation=explanation,
        context={'target': str(target), 'url': url, 'domain': _domain(url), 'active_domain': ((run_context.get('captured_context') or {}).get('target_fingerprint') or {}).get('browser_domain')},
    ))
    return events


def events_for_step(run_id: str, step, result: dict, run_context: dict | None = None) -> list[dict]:
    run_context = run_context or get_run_context(run_id) or {}
    action = getattr(step, 'action_type', '')
    if action in CLIPBOARD_READ_ACTIONS or action in CLIPBOARD_WRITE_ACTIONS:
        return _clipboard_event(run_id, step, result, run_context)
    if action in FILE_ACTIONS:
        return _file_event(run_id, step, result)
    if action in BROWSER_ACTIONS:
        return _browser_events(run_id, step, result, run_context)
    return []


def record_step_events(run_id: str, step, result: dict, run_context: dict | None = None) -> list[dict]:
    events = events_for_step(run_id, step, result, run_context)
    for event in events:
        record_guardian_event(event)
        append_run_history(run_id, 'guardian_events', event, limit=40)
    return events
