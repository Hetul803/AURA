from __future__ import annotations

import time

from .state import get_run_context, update_run_context


def now_ts() -> float:
    return time.time()


def normalize_timestamp(value: float | int | None) -> float | None:
    if value is None:
        return None
    stamp = float(value)
    if stamp > 10**11:
        return stamp / 1000.0
    return stamp


def _duration_ms(start: float | None, end: float | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int(round((end - start) * 1000)))


def initial_hero_timing(*, proactive: dict | None = None, assist_run: bool = False) -> dict:
    hero = ((proactive or {}).get('hero_timing') or {}) if isinstance(proactive, dict) else {}
    marks = {
        'run_started_at': now_ts(),
        'overlay_invoked_at': normalize_timestamp(hero.get('overlay_invoked_at')),
        'overlay_visible_at': normalize_timestamp(hero.get('overlay_visible_at')),
        'overlay_submitted_at': normalize_timestamp(hero.get('overlay_submitted_at')),
        'context_capture_completed_at': None,
        'model_request_started_at': None,
        'model_request_completed_at': None,
        'approval_wait_started_at': None,
        'approval_received_at': None,
        'pasteback_started_at': None,
        'pasteback_completed_at': None,
        'run_completed_at': None,
    }
    phase = 'capturing' if assist_run else 'running'
    timing = {
        'marks': marks,
        'durations_ms': {},
        'phase': phase,
        'phase_label': 'Capturing context' if assist_run else 'Running',
        'detail': 'Preparing the current request.' if assist_run else 'Running command.',
        'transitions': [],
        'updated_at': now_ts(),
    }
    timing['durations_ms'] = derive_durations(timing)
    return timing


def derive_durations(hero_timing: dict | None) -> dict:
    marks = (hero_timing or {}).get('marks') or {}
    return {
        'hotkey_to_overlay_visible': _duration_ms(marks.get('overlay_invoked_at'), marks.get('overlay_visible_at')),
        'overlay_submit_to_context_capture_complete': _duration_ms(marks.get('overlay_submitted_at'), marks.get('context_capture_completed_at')),
        'context_capture_to_model_request_start': _duration_ms(marks.get('context_capture_completed_at'), marks.get('model_request_started_at')),
        'model_request_duration': _duration_ms(marks.get('model_request_started_at'), marks.get('model_request_completed_at')),
        'approval_wait_duration': _duration_ms(marks.get('approval_wait_started_at'), marks.get('approval_received_at')),
        'approval_to_pasteback_start': _duration_ms(marks.get('approval_received_at'), marks.get('pasteback_started_at')),
        'pasteback_duration': _duration_ms(marks.get('pasteback_started_at'), marks.get('pasteback_completed_at')),
        'total_run_duration': _duration_ms(marks.get('run_started_at'), marks.get('run_completed_at')),
    }


def hero_timing_for(run_id: str) -> dict:
    ctx = get_run_context(run_id) or {}
    hero_timing = ctx.get('hero_timing') or initial_hero_timing(proactive=None, assist_run=False)
    hero_timing['durations_ms'] = derive_durations(hero_timing)
    return hero_timing


def mark_hero_timing(run_id: str, mark: str, *, timestamp: float | int | None = None, overwrite: bool = False) -> dict:
    ctx = get_run_context(run_id) or {}
    hero_timing = ctx.get('hero_timing') or initial_hero_timing(proactive=None, assist_run=False)
    marks = dict(hero_timing.get('marks') or {})
    if overwrite or marks.get(mark) is None:
        marks[mark] = normalize_timestamp(timestamp if timestamp is not None else now_ts())
    hero_timing = {**hero_timing, 'marks': marks, 'updated_at': now_ts()}
    hero_timing['durations_ms'] = derive_durations(hero_timing)
    update_run_context(run_id, {'hero_timing': hero_timing})
    return hero_timing


def set_hero_phase(run_id: str, phase: str, *, label: str | None = None, detail: str | None = None) -> dict:
    ctx = get_run_context(run_id) or {}
    hero_timing = ctx.get('hero_timing') or initial_hero_timing(proactive=None, assist_run=False)
    transitions = list(hero_timing.get('transitions') or [])
    transition = {
        'phase': phase,
        'label': label or hero_timing.get('phase_label') or phase.replace('_', ' ').title(),
        'detail': detail or hero_timing.get('detail') or '',
        'timestamp': now_ts(),
    }
    if not transitions or transitions[-1].get('phase') != phase:
        transitions.append(transition)
    hero_timing = {
        **hero_timing,
        'phase': phase,
        'phase_label': transition['label'],
        'detail': transition['detail'],
        'transitions': transitions[-12:],
        'updated_at': transition['timestamp'],
    }
    hero_timing['durations_ms'] = derive_durations(hero_timing)
    update_run_context(run_id, {'hero_timing': hero_timing, 'hero_phase': phase})
    return hero_timing
