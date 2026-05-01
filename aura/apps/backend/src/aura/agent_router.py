from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

from .cost_router import route_model
from .learning import list_workflow_memory
from .memory_engine import search_memory_items


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    name: str
    role: str
    status: str
    description: str
    strengths: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    privacy: str = 'local_first'
    cost_tier: str = 'unknown'
    approval_required_for: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _codex_available() -> bool:
    return bool(os.environ.get('AURA_CODEX_ENABLED') == '1' or os.environ.get('CODEX_HOME'))


def list_agents() -> list[dict[str, Any]]:
    codex_status = 'available' if _codex_available() else 'configured_later'
    return [
        AgentSpec(
            agent_id='local-code-worker',
            name='Local Code Worker',
            role='coding',
            status='available',
            description='Runs local commands and deterministic repair strategies inside the current machine.',
            strengths=['run_tests', 'diagnose_tracebacks', 'repair_simple_python', 'verify_locally'],
            constraints=['limited_semantic_coding', 'no_large_refactors_without_codex'],
            cost_tier='local',
            approval_required_for=['destructive_shell', 'git_push', 'dependency_install'],
        ).to_dict(),
        AgentSpec(
            agent_id='codex-coding-agent',
            name='Codex Coding Agent',
            role='coding',
            status=codex_status,
            description='External coding worker for larger code changes, repo implementation tasks, tests, and repair loops.',
            strengths=['multi_file_edits', 'repo_analysis', 'test_driven_repairs', 'frontend_backend_work'],
            constraints=['requires_connector_or_cli', 'must_follow_aura_policy', 'must_not_push_without_approval'],
            cost_tier='premium',
            approval_required_for=['write_code', 'run_commands', 'git_commit', 'git_push'],
        ).to_dict(),
        AgentSpec(
            agent_id='reasoning-llm',
            name='Reasoning LLM',
            role='reasoning',
            status='available',
            description='Current configured model path for planning, writing, summarization, and extraction.',
            strengths=['planning', 'summarization', 'drafting', 'classification'],
            constraints=['route_sensitive_context_by_policy', 'prefer_local_for_private_simple_tasks'],
            cost_tier='variable',
            approval_required_for=['cloud_sensitive_context'],
        ).to_dict(),
        AgentSpec(
            agent_id='browser-agent',
            name='Browser Agent',
            role='browser',
            status='available',
            description='Visible or fixture-backed browser worker for reading, navigation, and web workflows.',
            strengths=['web_read', 'navigation', 'form_context'],
            constraints=['confirm_submissions', 'confirm_uploads', 'confirm_purchases'],
            cost_tier='local',
            approval_required_for=['submit_form', 'upload_file', 'purchase'],
        ).to_dict(),
        AgentSpec(
            agent_id='future-device-agent',
            name='Future Device Agent',
            role='device',
            status='planned',
            description='Placeholder for phone, home, car, wearable, and enterprise agents using the same routing contract.',
            strengths=['cross_device_handoff_later', 'mobile_approval_later', 'enterprise_policy_later'],
            constraints=['not_implemented_yet'],
            cost_tier='unknown',
            approval_required_for=['device_control'],
        ).to_dict(),
    ]


def get_agent(agent_id: str) -> dict[str, Any] | None:
    return next((agent for agent in list_agents() if agent['agent_id'] == agent_id), None)


def diagnose_breakage(observation: dict[str, Any] | None) -> dict[str, Any]:
    obs = observation or {}
    failure_class = obs.get('failure_class') or 'unknown_error'
    detail = obs.get('failure_detail') or obs.get('stderr') or obs.get('last_error') or ''
    traceback_excerpt = obs.get('traceback_excerpt') or ''
    repairable = bool(obs.get('repairable') or failure_class in {'syntax_error', 'name_error'})
    requires_user = bool(obs.get('requires_user') or failure_class in {'dependency_error', 'permission_error'})
    recommendations = {
        'syntax_error': 'Ask the coding worker to inspect the failing file and repair syntax before rerunning tests.',
        'name_error': 'Ask the coding worker to identify the missing or misspelled symbol and rerun the command.',
        'dependency_error': 'Ask the user before installing dependencies or changing the environment.',
        'permission_error': 'Ask for permission or a safer target path before retrying.',
        'runtime_error': 'Escalate to a coding agent with the traceback and current test command.',
        'unknown_error': 'Collect more logs, rerun the smallest reproduction, then escalate if still unclear.',
    }
    return {
        'failure_class': failure_class,
        'detail': detail,
        'traceback_excerpt': traceback_excerpt,
        'repairable': repairable,
        'requires_user': requires_user,
        'recommended_action': recommendations.get(failure_class, recommendations['unknown_error']),
    }


def build_agent_prompt(
    *,
    task: str,
    route: dict[str, Any],
    context: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
) -> str:
    ctx = context or {}
    workspace = ctx.get('workspace') or ctx.get('workspace_hint') or ((ctx.get('project') or {}).get('current_folder')) or ''
    repo = ctx.get('current_repo') or ((ctx.get('project') or {}).get('current_repo')) or ''
    memory = search_memory_items(task, kind=None, scope='personal', limit=5)
    memory_lines = [f"- {item['kind']} / {item['memory_key']}: {item['value']}" for item in memory]
    diagnosis_lines = []
    if diagnosis:
        diagnosis_lines = [
            f"- failure_class: {diagnosis.get('failure_class')}",
            f"- detail: {diagnosis.get('detail')}",
            f"- recommended_action: {diagnosis.get('recommended_action')}",
        ]
        if diagnosis.get('traceback_excerpt'):
            diagnosis_lines.append(f"- traceback_excerpt: {diagnosis.get('traceback_excerpt')}")

    return '\n'.join([
        'You are a coding worker inside AURA, the user-owned AI operating layer.',
        'Follow AURA policy: inspect first, make scoped edits only, protect secrets, do not delete, do not push without approval.',
        f'Task: {task}',
        f'Chosen worker: {route.get("agent_id")} ({route.get("reason")})',
        f'Workspace: {workspace or "unknown"}',
        f'Repository: {repo or "unknown"}',
        'Relevant memory:',
        *(memory_lines or ['- none']),
        'Known breakage:',
        *(diagnosis_lines or ['- none']),
        'Required loop:',
        '- understand intent and current repo state',
        '- identify the smallest failing reproduction or test',
        '- implement the minimal repair',
        '- run relevant tests',
        '- summarize changed files, verification, risks, and next step',
    ])


def route_agent(
    *,
    task: str,
    task_type: str | None = None,
    context: dict[str, Any] | None = None,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_l = task.lower()
    task_type = task_type or 'generic'
    diagnosis = diagnose_breakage(observation) if observation else None
    coding_signal = any(token in task_l for token in ['code', 'repo', 'bug', 'test', 'build', 'app', 'implement', 'repair', 'fix'])
    if task_type.startswith('code:') or coding_signal:
        if _codex_available() and any(token in task_l for token in ['build', 'implement', 'refactor', 'app', 'multi-file', 'frontend', 'backend']):
            agent_id = 'codex-coding-agent'
            reason = 'coding task needs repo-level implementation and Codex is configured'
        else:
            agent_id = 'local-code-worker'
            reason = 'local worker can run commands, diagnose failures, and apply deterministic repairs now'
    elif any(token in task_l for token in ['website', 'browser', 'page', 'gmail']):
        agent_id = 'browser-agent'
        reason = 'task depends on browser context or web interaction'
    else:
        agent_id = 'reasoning-llm'
        reason = 'task is primarily reasoning, writing, summarization, or classification'

    agent = get_agent(agent_id) or {}
    route = {
        'agent_id': agent_id,
        'agent': agent,
        'task_type': task_type,
        'reason': reason,
        'diagnosis': diagnosis,
        'approval_required_for': agent.get('approval_required_for', []),
        'status': agent.get('status'),
        'model_route': route_model(
            purpose='coding' if agent_id in {'local-code-worker', 'codex-coding-agent'} else 'planning',
            prompt=task,
            privacy='normal',
            complexity='hard' if agent_id == 'codex-coding-agent' else 'simple',
            allow_cloud=False,
            prefer_user_subscription=agent_id == 'browser-agent',
        ),
    }
    route['agent_prompt'] = build_agent_prompt(task=task, route=route, context=context, diagnosis=diagnosis)
    return route


def workflow_suggestions(limit: int = 10) -> list[dict[str, Any]]:
    suggestions = []
    for row in list_workflow_memory():
        evidence = int(row.get('success_count') or 0) + int(row.get('failure_count') or 0)
        if evidence <= 0:
            continue
        suggestions.append({
            'task_type': row.get('task_type'),
            'pattern_key': row.get('pattern_key'),
            'strategy': row.get('strategy'),
            'confidence': row.get('confidence'),
            'evidence_count': evidence,
            'success_count': row.get('success_count'),
            'failure_count': row.get('failure_count'),
            'notes': row.get('notes'),
            'suggested_workflow_name': f"{row.get('task_type')} / {row.get('pattern_key')}",
            'automation_ready': evidence >= 2 and float(row.get('confidence') or 0) >= 0.55,
        })
    return sorted(suggestions, key=lambda item: (item['automation_ready'], item['confidence'], item['evidence_count']), reverse=True)[:limit]
