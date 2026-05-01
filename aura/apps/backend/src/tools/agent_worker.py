from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import UTC, datetime

from aura.agent_router import route_agent
from storage.profile_paths import profile_dir
from tools.tool_result import failure, success


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _job_dir(job_id: str):
    path = profile_dir() / 'agent_jobs' / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_job_artifacts(*, route: dict, task: str, context: dict, observation: dict | None) -> dict:
    job_id = f"job_{uuid.uuid4().hex}"
    path = _job_dir(job_id)
    prompt_path = path / 'AGENT_PROMPT.md'
    metadata_path = path / 'job.json'
    prompt_path.write_text(route['agent_prompt'], encoding='utf-8')
    metadata = {
        'job_id': job_id,
        'created_at': _now(),
        'status': 'ready',
        'task': task,
        'agent_id': route['agent_id'],
        'route_reason': route['reason'],
        'context': context,
        'observation': observation or {},
        'prompt_path': str(prompt_path),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True, default=str), encoding='utf-8')
    return {'job_id': job_id, 'job_dir': str(path), 'prompt_path': str(prompt_path), 'metadata_path': str(metadata_path), 'metadata': metadata}


def _maybe_execute_codex(prompt: str, cwd: str | None = None) -> dict:
    if os.getenv('AURA_CODEX_EXECUTE') != '1':
        return {'executed': False, 'reason': 'codex_execution_disabled'}
    command = os.getenv('AURA_CODEX_COMMAND') or shutil.which('codex')
    if not command:
        return {'executed': False, 'reason': 'codex_command_not_found'}
    proc = subprocess.run(
        [command, 'exec', '--skip-git-repo-check'],
        input=prompt,
        cwd=cwd or None,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=int(os.getenv('AURA_CODEX_TIMEOUT_SECONDS', '900')),
    )
    return {
        'executed': True,
        'exit_code': proc.returncode,
        'stdout': proc.stdout[-4000:],
        'stderr': proc.stderr[-4000:],
        'ok': proc.returncode == 0,
    }


def handle_agent_action(step, run_context: dict | None = None) -> dict:
    if step.action_type != 'AGENT_DELEGATE':
        return failure(step.action_type, error='unsupported_agent_action')
    args = step.args or {}
    task = args.get('task') or (run_context or {}).get('text') or step.name
    context = args.get('context') or (run_context or {}).get('planning_context') or ((run_context or {}).get('plan') or {}).get('context') or {}
    observation = args.get('observation') or (run_context or {}).get('last_observation')
    route = route_agent(
        task=task,
        task_type=args.get('task_type') or ((run_context or {}).get('plan') or {}).get('signature'),
        context=context,
        observation=observation,
    )
    job = _write_job_artifacts(route=route, task=task, context=context, observation=observation)
    workspace = context.get('workspace') or context.get('workspace_hint') or ((context.get('project') or {}).get('current_folder'))
    execution = _maybe_execute_codex(route['agent_prompt'], cwd=workspace) if route['agent_id'] == 'codex-coding-agent' else {'executed': False, 'reason': 'local_worker_bridge_ready'}
    return success(
        'AGENT_DELEGATE',
        result={'route': route, 'agent_prompt': route['agent_prompt'], 'agent_job': job, 'execution': execution},
        observation={
            'agent_id': route['agent_id'],
            'route_reason': route['reason'],
            'agent_status': route.get('status'),
            'task_type': route.get('task_type'),
            'agent_job_id': job['job_id'],
            'agent_job_status': 'executed' if execution.get('executed') else 'ready',
            'codex_executed': bool(execution.get('executed')),
        },
        artifacts=[job['prompt_path'], job['metadata_path']],
    )
