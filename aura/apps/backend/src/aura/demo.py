from __future__ import annotations

import json
import os
import re
from pathlib import Path

from tools.os_automation import write_clipboard
from tools.tool_result import failure, success

FIXTURE_DIR = Path(__file__).resolve().parents[2] / 'fixtures' / 'demo'


def demo_mode_enabled() -> bool:
    return os.getenv('AURA_DEMO_MODE', '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _read_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def demo_scenarios() -> list[dict]:
    scenarios = []
    if not FIXTURE_DIR.exists():
        return scenarios
    for path in sorted(FIXTURE_DIR.glob('*.json')):
        payload = _read_fixture(path)
        scenarios.append({
            'id': payload['id'],
            'label': payload['label'],
            'description': payload['description'],
            'command': payload['command'],
            'task_kind': payload['task_kind'],
        })
    return scenarios


def demo_scenario(scenario_id: str | None) -> dict | None:
    if not scenario_id:
        return None
    path = FIXTURE_DIR / f'{scenario_id}.json'
    if not path.exists():
        return None
    return _read_fixture(path)


def build_demo_metadata(proactive: dict | None = None) -> dict:
    incoming = ((proactive or {}).get('demo') or {}) if isinstance(proactive, dict) else {}
    scenario_id = incoming.get('scenario_id')
    scenario = demo_scenario(scenario_id) if scenario_id else None
    enabled = bool(incoming.get('enabled') or demo_mode_enabled() or scenario)
    metadata = {
        'enabled': enabled,
        'scenario_id': scenario_id if scenario else None,
        'scenario_label': scenario.get('label') if scenario else None,
        'command': scenario.get('command') if scenario else None,
        'task_kind': scenario.get('task_kind') if scenario else None,
        'used_fixture_context': False,
        'used_model_fallback': False,
        'used_copy_fallback': False,
        'fallbacks': [],
        'status': 'idle' if enabled else 'disabled',
    }
    return metadata


def demo_run_payload(scenario_id: str) -> dict:
    scenario = demo_scenario(scenario_id)
    if not scenario:
        raise KeyError(scenario_id)
    return {
        'text': scenario['command'],
        'proactive': {
            'demo': {
                'enabled': True,
                'scenario_id': scenario_id,
            },
        },
    }


def demo_context_for_run(run_context: dict | None) -> dict | None:
    ctx = run_context or {}
    demo = ctx.get('demo') or {}
    scenario = demo_scenario(demo.get('scenario_id'))
    if not (demo.get('enabled') and scenario):
        return None
    payload = dict(scenario.get('captured_context') or {})
    payload.setdefault('ok', True)
    payload.setdefault('warnings', [])
    if 'demo_context_used' not in payload['warnings']:
        payload['warnings'].append('demo_context_used')
    payload['input_source'] = payload.get('input_source') or 'demo_fixture'
    payload['capture_path_used'] = payload.get('capture_path_used') or 'demo_fixture'
    capture = dict(payload.get('capture_method') or {})
    capture.setdefault('selection_copy_attempted', False)
    capture.setdefault('selection_copy_succeeded', False)
    capture.setdefault('clipboard_fallback_used', False)
    capture.setdefault('clipboard_preserved', True)
    capture.setdefault('clipboard_restored_after_capture', True)
    capture.setdefault('capture_failure_reason', 'demo_fixture_context')
    payload['capture_method'] = capture
    payload.setdefault('selected_text', '')
    payload.setdefault('clipboard_text', payload.get('input_text', ''))
    payload.setdefault('paste_target', payload.get('target_fingerprint') or {})
    return payload


def _compact_text(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '')).strip()


def _sentences(text: str) -> list[str]:
    value = _compact_text(text)
    if not value:
        return []
    parts = re.split(r'(?<=[.!?])\s+', value)
    return [part.strip() for part in parts if part.strip()]


def _bullets(items: list[str], limit: int = 3) -> str:
    return '\n'.join(f'- {item}' for item in items[:limit])


def demo_draft_fallback(*, task_kind: str, source_text: str, request_text: str, research_context: dict, style_hints: dict[str, str]) -> dict:
    source = _compact_text(source_text)
    parts = _sentences(source)
    tone = style_hints.get('tone', 'polished')
    length = style_hints.get('length', 'concise')
    opener = 'Hi,' if tone == 'polished' else 'Hi,'
    if task_kind == 'reply':
        summary = parts[0] if parts else source[:160]
        detail = parts[1] if len(parts) > 1 and length != 'concise' else ''
        lines = [
            opener,
            '',
            f'Thanks for the note. {summary}',
        ]
        if detail:
            lines.append(detail)
        lines.extend(['', 'Best,'])
        draft_text = '\n'.join(lines).strip()
    elif task_kind in {'answer', 'research_and_respond'}:
        key_points = list((research_context or {}).get('key_points') or [])
        if not key_points and parts:
            key_points = parts[:3]
        intro = parts[0] if parts else _compact_text(request_text) or 'Here is the answer.'
        draft_text = f'Answer: {intro}\n\nKey points:\n{_bullets(key_points or [intro])}'
        sources = list((research_context or {}).get('sources') or [])
        if sources:
            draft_text += f"\n\nSources:\n{_bullets(sources, limit=2)}"
    elif task_kind == 'rewrite':
        base = parts or [source]
        refined = []
        for idx, sentence in enumerate(base):
            normalized = sentence[:1].upper() + sentence[1:] if sentence else sentence
            if idx == 0 and not normalized.endswith('.'):
                normalized += '.'
            refined.append(normalized)
        draft_text = ' '.join(refined).strip()
    elif task_kind == 'explain':
        intro = parts[0] if parts else source
        follow_up = parts[1] if len(parts) > 1 else ''
        draft_text = f'In plain terms: {intro}'
        if follow_up:
            draft_text += f' {follow_up}'
    else:
        focus = parts[:2] if parts else [source]
        draft_text = 'Summary:\n' + _bullets(focus, limit=2)
    return {
        'draft_text': draft_text.strip(),
        'style_signals_used': dict(style_hints),
        'research_used': bool((research_context or {}).get('search_used')),
        'provider': 'demo_fallback',
        'model': 'deterministic',
        'fallback_used': True,
        'confidence': 0.55,
        'notes': ['demo_mode_model_fallback'],
    }


def demo_copy_result(text: str, *, reason: str) -> dict:
    copied = write_clipboard(text)
    copied_ok = copied.get('ok')
    observation = {
        'target_validation': 'demo_copy_fallback',
        'target_validation_result': 'copied' if copied_ok else 'copy_ready',
        'strict_validation': False,
        'cautious_validation': False,
        'paste_attempted': False,
        'paste_blocked_reason': reason,
        'context_drift_reason': reason,
        'clipboard_preserved': copied_ok,
        'clipboard_restored_after_paste': copied_ok,
        'clipboard_restore_error_after_paste': None if copied_ok else copied.get('error'),
        'demo_copy_fallback': True,
    }
    if copied_ok:
        return success('OS_PASTE', result={'pasted': 0, 'copied': len(text)}, observation=observation, safety_flags=['clipboard_write'])
    return success('OS_PASTE', result={'pasted': 0, 'copied': 0, 'copy_ready': len(text)}, observation=observation)
