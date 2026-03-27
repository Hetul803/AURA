from __future__ import annotations

import json
import threading
from collections import defaultdict
from pathlib import Path

from storage.db import get_conn
from storage.profile_paths import profile_dir

PANIC = False
RUN_CANCEL: dict[str, bool] = defaultdict(bool)
RUN_CONTEXT: dict[str, dict] = {}
SAFETY_EVENTS: list[dict] = []
GUARDIAN_EVENTS: list[dict] = []
LOCK = threading.Lock()
_RUN_CONTEXT_LIMIT = 30


def _run_context_dir() -> Path:
    path = profile_dir() / 'run_contexts'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_context_path(run_id: str) -> Path:
    return _run_context_dir() / f'{run_id}.json'


def _safe_json_dump(payload: dict) -> None:
    run_id = payload.get('run_id')
    if not run_id:
        return
    path = _run_context_path(run_id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding='utf-8')


def _load_run_context(run_id: str) -> dict | None:
    path = _run_context_path(run_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _trim_persisted_run_contexts() -> None:
    paths = sorted(_run_context_dir().glob('*.json'), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in paths[_RUN_CONTEXT_LIMIT:]:
        path.unlink(missing_ok=True)



def db_conn():
    return get_conn()



def set_panic(v: bool):
    global PANIC
    PANIC = v



def is_panic() -> bool:
    return PANIC



def cancel_run(run_id: str):
    with LOCK:
        RUN_CANCEL[run_id] = True



def is_run_cancelled(run_id: str) -> bool:
    with LOCK:
        return RUN_CANCEL.get(run_id, False) or PANIC



def set_run_context(run_id: str, context: dict):
    with LOCK:
        payload = {**context, 'run_id': context.get('run_id') or run_id}
        RUN_CONTEXT[run_id] = payload
        _safe_json_dump(payload)
        _trim_persisted_run_contexts()



def update_run_context(run_id: str, patch: dict):
    with LOCK:
        current = RUN_CONTEXT.get(run_id) or _load_run_context(run_id) or {'run_id': run_id}
        RUN_CONTEXT[run_id] = {**current, **patch, 'run_id': current.get('run_id') or run_id}
        _safe_json_dump(RUN_CONTEXT[run_id])
        _trim_persisted_run_contexts()
        return RUN_CONTEXT[run_id]



def append_run_history(run_id: str, key: str, item: dict, limit: int = 20):
    with LOCK:
        current = RUN_CONTEXT.get(run_id) or _load_run_context(run_id) or {'run_id': run_id}
        history = list(current.get(key, []))
        history.append(item)
        RUN_CONTEXT[run_id] = {**current, key: history[-limit:], 'run_id': current.get('run_id') or run_id}
        _safe_json_dump(RUN_CONTEXT[run_id])
        _trim_persisted_run_contexts()
        return RUN_CONTEXT[run_id][key]



def increment_run_counter(run_id: str, key: str, amount: int = 1):
    with LOCK:
        current = RUN_CONTEXT.get(run_id) or _load_run_context(run_id) or {'run_id': run_id}
        current_value = int(current.get(key, 0))
        RUN_CONTEXT[run_id] = {**current, key: current_value + amount, 'run_id': current.get('run_id') or run_id}
        _safe_json_dump(RUN_CONTEXT[run_id])
        _trim_persisted_run_contexts()
        return RUN_CONTEXT[run_id][key]



def get_run_context(run_id: str) -> dict | None:
    with LOCK:
        payload = RUN_CONTEXT.get(run_id)
        if payload is not None:
            return payload
        loaded = _load_run_context(run_id)
        if loaded is not None:
            RUN_CONTEXT[run_id] = loaded
        return loaded



def list_runs() -> dict[str, dict]:
    with LOCK:
        cached = dict(RUN_CONTEXT)
    for path in _run_context_dir().glob('*.json'):
        run_id = path.stem
        if run_id not in cached:
            loaded = _load_run_context(run_id)
            if loaded is not None:
                cached[run_id] = loaded
    return cached



def record_safety_event(evt: dict):
    with LOCK:
        SAFETY_EVENTS.append(evt)
        del SAFETY_EVENTS[:-200]



def list_safety_events() -> list[dict]:
    with LOCK:
        return list(SAFETY_EVENTS)



def record_guardian_event(evt: dict):
    with LOCK:
        GUARDIAN_EVENTS.append(evt)
        del GUARDIAN_EVENTS[:-200]



def list_guardian_events(*, run_id: str | None = None, limit: int = 50) -> list[dict]:
    with LOCK:
        items = list(GUARDIAN_EVENTS)
    if run_id:
        items = [item for item in items if item.get('run_id') == run_id]
    return items[-max(1, limit):][::-1]
