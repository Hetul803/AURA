from __future__ import annotations

import json
import queue

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from aura.assist import capture_structured_context
from aura.agent_router import get_agent, list_agents, route_agent, workflow_suggestions
from aura.context_engine import capture_current_context, latest_context_snapshot, list_context_snapshots
from aura.cost_router import (
    list_usage_events,
    model_candidates,
    put_cached_response,
    record_model_usage,
    route_model,
    set_budget,
    usage_summary,
)
from devices.adapters import get_device_adapter, list_device_adapters
from aura.learning import (
    consolidate_learning,
    list_preference_memory,
    list_reflection_records,
    list_safety_memory,
    list_site_memory,
    list_workflow_memory,
    query_relevant_memory,
)
from aura.macros import list_macros
from aura.memory import delete_memory, list_memories, update_memory
from aura.memory_engine import (
    archive_memory_item,
    delete_memory_item,
    list_memory_items,
    remember_item,
    search_memory_items,
    update_memory_item,
)
from aura.models import available_models
from aura.orchestrator import approve_run, reject_run, resume_run, retry_assist_run, run_command
from aura.planner import plan_from_text
from aura.prefs import get_prefs, reset_all, reset_pref, set_pref
from aura.state import cancel_run, db_conn, get_run_context, list_audit_log, list_run_events, list_safety_events, record_run_event, set_panic
from aura.user_tools import build_user_ai_prompt, get_user_web_tool, list_user_web_tools
from aura.workflow_engine import (
    create_workflow,
    delete_workflow,
    get_workflow,
    list_workflows,
    render_workflow_command,
    suggested_workflow_templates,
    update_workflow,
)
from storage.export_import import export_profile, import_profile
from storage.migrations import run_migrations
from storage.profile_paths import profile_dir
from storage.retention import enforce_retention
from storage.snapshots import create_snapshot
from tools.browser_runtime import browser_manager
from tools.registry import actions_for_device, get_tool_spec, list_tool_specs

run_migrations()
app = FastAPI(title='AURA Backend')
EVENTS: dict[str, queue.Queue[str]] = {}


def _emit(run_id: str, e: dict):
    EVENTS.setdefault(run_id, queue.Queue()).put(json.dumps(e))


class Cmd(BaseModel):
    text: str
    choices: dict = {}
    use_macro: bool = False
    context: dict | None = None


class PanicBody(BaseModel):
    run_id: str | None = None


class MemoryPatch(BaseModel):
    value: str | None = None
    pinned: int | None = None


class MemoryItemCreate(BaseModel):
    kind: str = 'note'
    key: str
    value: str
    scope: str = 'personal'
    permission: str = 'private'
    tags: list[str] = []
    confidence: float = 0.5
    source: str = 'manual'
    pinned: bool = False
    metadata: dict = {}


class MemoryItemPatch(BaseModel):
    kind: str | None = None
    key: str | None = None
    value: str | None = None
    scope: str | None = None
    permission: str | None = None
    tags: list[str] | None = None
    confidence: float | None = None
    source: str | None = None
    pinned: bool | None = None
    archived: bool | None = None
    metadata: dict | None = None


class MemorySearchBody(BaseModel):
    query: str
    kind: str | None = None
    scope: str | None = None
    limit: int = 10


class AgentRouteBody(BaseModel):
    task: str
    task_type: str | None = None
    context: dict | None = None
    observation: dict | None = None


class CostRouteBody(BaseModel):
    purpose: str = 'planning'
    prompt: str = ''
    privacy: str = 'normal'
    complexity: str = 'simple'
    allow_cloud: bool = False
    prefer_user_subscription: bool = False


class CostUsageBody(BaseModel):
    run_id: str | None = None
    route: dict
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    metadata: dict = {}


class CostBudgetBody(BaseModel):
    scope: str = 'personal'
    monthly_limit_usd: float | None = None
    warn_at_usd: float | None = None


class CostCacheBody(BaseModel):
    purpose: str
    prompt: str
    provider: str
    model: str
    response: dict


class UserToolPromptBody(BaseModel):
    task: str
    tool_id: str = 'chatgpt'
    mode: str = 'general'
    context: dict | None = None


class WorkflowCreateBody(BaseModel):
    name: str
    command_template: str
    description: str = ''
    trigger_type: str = 'manual'
    trigger_value: str = ''
    enabled: bool = True
    approval_policy: str = 'ask_for_risky_actions'
    source: str = 'manual'
    confidence: float = 0.5
    metadata: dict = {}


class WorkflowPatchBody(BaseModel):
    name: str | None = None
    command_template: str | None = None
    description: str | None = None
    trigger_type: str | None = None
    trigger_value: str | None = None
    enabled: bool | None = None
    approval_policy: str | None = None
    source: str | None = None
    confidence: float | None = None
    metadata: dict | None = None


class WorkflowRenderBody(BaseModel):
    variables: dict = {}


class LearningQuery(BaseModel):
    task_type: str | None = None
    domain: str | None = None
    failure_class: str | None = None
    action_key: str | None = None
    limit: int = 5


class ApprovalBody(BaseModel):
    text: str | None = None


class RetryBody(BaseModel):
    feedback: str | None = None


class RejectBody(BaseModel):
    reason: str | None = None


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


@app.get('/tools')
def tools_list(device_adapter: str | None = None):
    if device_adapter:
        return actions_for_device(device_adapter)
    return list_tool_specs()


@app.get('/tools/{action_type}')
def tools_get(action_type: str):
    spec = get_tool_spec(action_type)
    if not spec:
        raise HTTPException(404, 'tool not registered')
    return spec


@app.get('/devices')
def devices_list():
    return list_device_adapters()


@app.get('/devices/{adapter_id}')
def devices_get(adapter_id: str):
    adapter = get_device_adapter(adapter_id)
    if not adapter:
        raise HTTPException(404, 'device adapter not registered')
    return adapter


@app.get('/agents')
def agents_list():
    return list_agents()


@app.post('/agents/route')
def agents_route(body: AgentRouteBody):
    return route_agent(task=body.task, task_type=body.task_type, context=body.context, observation=body.observation)


@app.get('/agents/workflow-suggestions')
def agents_workflow_suggestions(limit: int = 10):
    return workflow_suggestions(limit=limit)


@app.get('/agents/{agent_id}')
def agents_get(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, 'agent not registered')
    return agent


@app.get('/cost/models')
def cost_models():
    return model_candidates()


@app.post('/cost/route')
def cost_route(body: CostRouteBody):
    return route_model(
        purpose=body.purpose,
        prompt=body.prompt,
        privacy=body.privacy,
        complexity=body.complexity,
        allow_cloud=body.allow_cloud,
        prefer_user_subscription=body.prefer_user_subscription,
    )


@app.post('/cost/usage')
def cost_usage(body: CostUsageBody):
    return record_model_usage(run_id=body.run_id, route=body.route, prompt_tokens=body.prompt_tokens, completion_tokens=body.completion_tokens, metadata=body.metadata)


@app.get('/cost/usage')
def cost_usage_list(limit: int = 100):
    return list_usage_events(limit=limit)


@app.get('/cost/summary')
def cost_summary():
    return usage_summary()


@app.post('/cost/budget')
def cost_budget(body: CostBudgetBody):
    return set_budget(scope=body.scope, monthly_limit_usd=body.monthly_limit_usd, warn_at_usd=body.warn_at_usd)


@app.post('/cost/cache')
def cost_cache_put(body: CostCacheBody):
    return put_cached_response(body.purpose, body.prompt, body.provider, body.model, body.response)


@app.get('/user-tools')
def user_tools_list():
    return list_user_web_tools()


@app.get('/user-tools/{tool_id}')
def user_tools_get(tool_id: str):
    tool = get_user_web_tool(tool_id)
    if not tool:
        raise HTTPException(404, 'user tool not registered')
    return tool


@app.post('/user-tools/prompt')
def user_tools_prompt(body: UserToolPromptBody):
    return build_user_ai_prompt(task=body.task, tool_id=body.tool_id, context=body.context, mode=body.mode)


@app.get('/workflows')
def workflows_list(include_disabled: bool = False, trigger_type: str | None = None):
    return list_workflows(include_disabled=include_disabled, trigger_type=trigger_type)


@app.post('/workflows')
def workflows_create(body: WorkflowCreateBody):
    return create_workflow(**body.model_dump())


@app.get('/workflows/suggestions')
def workflows_suggestions(limit: int = 10):
    return suggested_workflow_templates(limit=limit)


@app.get('/workflows/{workflow_id}')
def workflows_get(workflow_id: str):
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(404, 'workflow not found')
    return workflow


@app.patch('/workflows/{workflow_id}')
def workflows_patch(workflow_id: str, body: WorkflowPatchBody):
    workflow = update_workflow(workflow_id, **body.model_dump(exclude_unset=True))
    if not workflow:
        raise HTTPException(404, 'workflow not found')
    return workflow


@app.post('/workflows/{workflow_id}/render')
def workflows_render(workflow_id: str, body: WorkflowRenderBody):
    rendered = render_workflow_command(workflow_id, body.variables)
    if not rendered:
        raise HTTPException(404, 'workflow not found')
    return rendered


@app.delete('/workflows/{workflow_id}')
def workflows_delete(workflow_id: str):
    if not delete_workflow(workflow_id):
        raise HTTPException(404, 'workflow not found')
    return {'ok': True}


@app.post('/plan')
def plan(cmd: Cmd):
    planned = plan_from_text(cmd.text, cmd.choices, cmd.context)
    return {**planned, 'steps': [s.model_dump() for s in planned.get('steps', [])]}


@app.post('/command')
def command(cmd: Cmd):
    run_id = 'pending'

    def emit(e):
        rid = e.get('run_id', run_id)
        _emit(rid, e)

    return run_command(cmd.text, emit, cmd.choices, cmd.use_macro, context=cmd.context)


@app.get('/context/current')
def context_current():
    return capture_current_context(source='api')


@app.get('/context/latest')
def context_latest():
    snapshot = latest_context_snapshot()
    if not snapshot:
        raise HTTPException(404, 'context snapshot not found')
    return snapshot


@app.get('/context/history')
def context_history(limit: int = 20):
    return list_context_snapshots(limit=limit)


@app.post('/assist/context')
def assist_context_capture():
    result = capture_structured_context()
    return result.get('result', {}).get('captured_context') or result


@app.post('/panic')
def panic(body: PanicBody):
    set_panic(True)
    if body.run_id:
        cancel_run(body.run_id)
        event = {'type': 'run_cancelled', 'run_id': body.run_id, 'status': 'cancelled', 'message': 'panic stop'}
        record_run_event(event)
        _emit(body.run_id, event)
    return {'panic': True, 'run_id': body.run_id}


@app.post('/panic/{run_id}')
def panic_run(run_id: str):
    cancel_run(run_id)
    event = {'type': 'run_cancelled', 'run_id': run_id, 'status': 'cancelled', 'message': 'panic stop'}
    record_run_event(event)
    _emit(run_id, event)
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


@app.post('/runs/{run_id}/approve')
def approve(run_id: str, body: ApprovalBody):
    def emit(e):
        _emit(run_id, e)

    return approve_run(run_id, body.text, emit)


@app.post('/runs/{run_id}/retry')
def retry(run_id: str, body: RetryBody):
    def emit(e):
        _emit(run_id, e)

    return retry_assist_run(run_id, body.feedback, emit)


@app.post('/runs/{run_id}/reject')
def reject(run_id: str, body: RejectBody):
    def emit(e):
        _emit(run_id, e)

    return reject_run(run_id, body.reason, emit)


@app.get('/runs/{run_id}')
def run_state(run_id: str):
    state = get_run_context(run_id)
    if not state:
        raise HTTPException(404, 'run not found')
    return state


@app.get('/runs/{run_id}/events')
def run_events(run_id: str):
    return list_run_events(run_id)


@app.get('/audit')
def audit(limit: int = 100):
    return list_audit_log(limit=limit)


@app.get('/runs/{run_id}/audit')
def run_audit(run_id: str, limit: int = 100):
    return list_audit_log(run_id=run_id, limit=limit)


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
        'snapshots_size': dir_size(base / 'snapshots'),
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


@app.get('/memory/items')
def memory_items_list(q: str | None = None, kind: str | None = None, scope: str | None = None, include_archived: bool = False, limit: int = 100):
    return list_memory_items(q=q, kind=kind, scope=scope, include_archived=include_archived, limit=limit)


@app.post('/memory/items')
def memory_items_create(body: MemoryItemCreate):
    return remember_item(
        kind=body.kind,
        key=body.key,
        value=body.value,
        scope=body.scope,
        permission=body.permission,
        tags=body.tags,
        confidence=body.confidence,
        source=body.source,
        pinned=body.pinned,
        metadata=body.metadata,
    )


@app.patch('/memory/items/{memory_id}')
def memory_items_patch(memory_id: str, patch: MemoryItemPatch):
    updated = update_memory_item(memory_id, **patch.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, 'memory item not found')
    return updated


@app.delete('/memory/items/{memory_id}')
def memory_items_delete(memory_id: str, archive: bool = True):
    ok = archive_memory_item(memory_id) if archive else delete_memory_item(memory_id)
    if not ok:
        raise HTTPException(404, 'memory item not found')
    return {'ok': True, 'archived': archive}


@app.post('/memory/search')
def memory_search(body: MemorySearchBody):
    return search_memory_items(body.query, kind=body.kind, scope=body.scope, limit=body.limit)


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


@app.get('/learning/reflections')
def learning_reflections(limit: int = 100):
    return list_reflection_records(limit=limit)


@app.get('/learning/memory/workflow')
def learning_workflow_memory():
    return list_workflow_memory()


@app.get('/learning/memory/preference')
def learning_preference_memory():
    return list_preference_memory()


@app.get('/learning/memory/site')
def learning_site_memory():
    return list_site_memory()


@app.get('/learning/memory/safety')
def learning_safety_memory():
    return list_safety_memory()


@app.post('/learning/query')
def learning_query(body: LearningQuery):
    return query_relevant_memory(
        task_type=body.task_type,
        domain=body.domain,
        failure_class=body.failure_class,
        action_key=body.action_key,
        limit=body.limit,
    )


@app.post('/learning/consolidate')
def learning_consolidate():
    return consolidate_learning()
