from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json, queue
from aura.orchestrator import run_command, resume_run
from aura.planner import plan_from_text
from aura.prefs import get_prefs, set_pref, reset_pref, reset_all
from aura.macros import list_macros
from aura.models import available_models
from aura.state import set_panic, cancel_run, get_run_context
from aura.memory import list_memories, update_memory, delete_memory
from storage.migrations import run_migrations
from storage.export_import import export_profile, import_profile
from storage.snapshots import create_snapshot
from storage.retention import enforce_retention
from aura.state import db_conn
from tools.browser_runtime import browser_manager
from storage.profile_paths import profile_dir
from aura.state import list_safety_events

run_migrations()
app = FastAPI(title='AURA Backend')
EVENTS: dict[str, "queue.Queue[str]"] = {}


def _emit(run_id: str, e: dict):
    EVENTS.setdefault(run_id, queue.Queue()).put(json.dumps(e))


class Cmd(BaseModel):
    text: str
    choices: dict = {}
    use_macro: bool = False


class PanicBody(BaseModel):
    run_id: str | None = None


class MemoryPatch(BaseModel):
    value: str | None = None
    pinned: int | None = None


@app.get('/health')
def health():
    return {'ok': True}


@app.get('/models')
def models():
    return available_models()


@app.post('/models/select')
def set_model(model_id: str):
    with db_conn() as conn:
        conn.execute("INSERT INTO profile_meta(key,value) VALUES('selected_model',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (model_id,))
    return {'ok': True, 'model_id': model_id}


@app.get('/models/select')
def get_model():
    row = db_conn().execute("SELECT value FROM profile_meta WHERE key='selected_model'").fetchone()
    return {'model_id': row['value'] if row else 'simple'}




@app.post('/plan')
def plan(cmd: Cmd):
    planned = plan_from_text(cmd.text, cmd.choices)
    return {**planned, 'steps': [s.model_dump() for s in planned.get('steps', [])]}

@app.post('/command')
def command(cmd: Cmd):
    run_id = 'pending'

    def emit(e):
        rid = e.get('run_id', run_id)
        _emit(rid, e)

    return run_command(cmd.text, emit, cmd.choices, cmd.use_macro)


@app.post('/panic')
def panic(body: PanicBody):
    set_panic(True)
    if body.run_id:
        cancel_run(body.run_id)
        _emit(body.run_id, {'type': 'run_cancelled', 'run_id': body.run_id, 'status': 'cancelled', 'message': 'panic stop'})
    return {'panic': True, 'run_id': body.run_id}


@app.post('/panic/{run_id}')
def panic_run(run_id: str):
    cancel_run(run_id)
    _emit(run_id, {'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled', 'message': 'panic stop'})
    return {'panic': True, 'run_id': run_id}


@app.post('/panic/reset')
def panic_reset():
    set_panic(False)
    return {'panic': False}


@app.post('/runs/{run_id}/resume')
def resume(run_id: str):
    def emit(e):
        _emit(run_id, e)

    return resume_run(run_id, emit)




@app.get('/runs/{run_id}')
def run_state(run_id: str):
    state = get_run_context(run_id)
    if not state:
        raise HTTPException(404, 'run not found')
    return state

@app.get('/events/stream/{run_id}')
def stream(run_id: str):
    q = EVENTS.setdefault(run_id, queue.Queue())

    def gen():
        idle = 0
        while idle < 75:
            try:
                item = q.get(timeout=0.2)
                idle = 0
                yield f"data: {item}\n\n"
            except Exception:
                idle += 1

    return StreamingResponse(gen(), media_type='text/event-stream')



@app.delete('/browser/session/{domain}')
def clear_browser_session(domain: str):
    browser_manager.clear_session(domain)
    return {'ok': True, 'domain': domain}


@app.get('/browser/sessions')
def list_browser_sessions():
    state_dir = profile_dir() / 'browser_state'
    sessions = []
    for f in state_dir.glob('*.json'):
        sessions.append({'domain': f.stem, 'path': str(f), 'size': f.stat().st_size})
    return sessions


@app.delete('/browser/sessions')
def clear_all_browser_sessions():
    state_dir = profile_dir() / 'browser_state'
    for f in state_dir.glob('*.json'):
        f.unlink(missing_ok=True)
    return {'ok': True}


@app.get('/safety/events')
def safety_events():
    return list_safety_events()


@app.get('/storage/stats')
def storage_stats():
    base = profile_dir()
    def dir_size(p):
        return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
    return {
      'profile_dir': str(base),
      'db_size': (base / 'aura.sqlite3').stat().st_size if (base / 'aura.sqlite3').exists() else 0,
      'artifacts_size': dir_size(base / 'artifacts'),
      'sessions_size': dir_size(base / 'browser_state'),
      'snapshots_size': dir_size(base / 'snapshots')
    }

@app.get('/preferences')
def prefs_list():
    return get_prefs()


@app.post('/preferences/{key}')
def prefs_set(key: str, value: str):
    set_pref(key, value)
    return {'ok': True}


@app.delete('/preferences/{key}')
def prefs_del(key: str):
    reset_pref(key)
    return {'ok': True}


@app.delete('/preferences')
def prefs_reset():
    reset_all()
    return {'ok': True}


@app.get('/macros')
def macros_list():
    return list_macros()


@app.get('/memories')
def memories(q: str | None = None):
    return list_memories(q)


@app.patch('/memories/{mid}')
def memories_patch(mid: int, patch: MemoryPatch):
    if not update_memory(mid, patch.value, patch.pinned):
        raise HTTPException(404, 'not found')
    return {'ok': True}


@app.delete('/memories/{mid}')
def memories_delete(mid: int):
    delete_memory(mid)
    return {'ok': True}


@app.post('/retention/sweep')
def retention_sweep():
    return enforce_retention()


@app.post('/profile/export')
def profile_export(path: str):
    return {'path': export_profile(path)}


@app.post('/profile/import')
def profile_import(path: str):
    import_profile(path)
    return {'ok': True}


@app.post('/profile/snapshot')
def snapshot():
    return {'snapshot': create_snapshot()}
