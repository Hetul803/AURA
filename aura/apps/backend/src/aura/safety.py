from __future__ import annotations

import re
import shlex
from urllib.parse import urlparse

from .learning import query_relevant_memory
from .privacy import detect_secret, redact_text
from tools.registry import get_tool_spec

SENSITIVE = ['send', 'delete', 'pay', 'purchase', 'checkout']
RISK_ORDER = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3, 'blocked': 4}
LOW_RISK_COMMANDS = {'ls', 'pwd', 'git status', 'git log', 'git diff', 'git branch', 'git remote', 'git rev-parse'}
MEDIUM_RISK_COMMANDS = {'npm install', 'pnpm install', 'pip install', 'python -m pip install', 'git checkout', 'git switch', 'git pull', 'git fetch'}
HIGH_RISK_TOKENS = {'rm', 'del', 'rmdir', 'mv', 'chmod', 'chown', 'sudo', 'su', 'mkfs', 'diskutil', 'dd', 'powershell', 'pwsh'}
BLOCKED_PATTERNS = [
    re.compile(r'(?i)\brm\s+-[^;&|]*r[^;&|]*\s+(/|~|\$HOME|/Users|/System|/Library)\b'),
    re.compile(r'(?i)\bdd\s+.*\bof=/dev/'),
    re.compile(r'(?i)\b(mkfs|diskpart|format)\b'),
    re.compile(r'(?i)\bcurl\b.*\|\s*(bash|sh|zsh|powershell|pwsh)\b'),
    re.compile(r'(?i)\bwget\b.*\|\s*(bash|sh|zsh|powershell|pwsh)\b'),
    re.compile(r'(?i)\b(env|printenv|cat)\b.*\|\s*(curl|nc|netcat)\b'),
]
LOCAL_DOMAINS = {'', 'localhost', '127.0.0.1', '::1'}


def requires_confirmation(step_name: str) -> bool:
    low = step_name.lower()
    return any(s in low for s in SENSITIVE)


def classify_shell_command(command: str, workspace: str | None = None) -> dict:
    command = (command or '').strip()
    lowered = re.sub(r'\s+', ' ', command.lower())
    if not command:
        return {'risk': 'blocked', 'requires_approval': False, 'blocked': True, 'reason': 'empty_shell_command'}
    if detect_secret(command):
        return {'risk': 'blocked', 'requires_approval': False, 'blocked': True, 'reason': 'command_contains_secret'}
    if any(pattern.search(command) for pattern in BLOCKED_PATTERNS):
        return {'risk': 'blocked', 'requires_approval': False, 'blocked': True, 'reason': 'destructive_or_exfiltrating_shell_command'}
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    first = tokens[0].lower() if tokens else ''
    first_two = ' '.join(token.lower() for token in tokens[:2])
    if first in HIGH_RISK_TOKENS or first_two in HIGH_RISK_TOKENS:
        return {'risk': 'high', 'requires_approval': True, 'blocked': False, 'reason': f'high_risk_shell_command:{first_two or first}'}
    if lowered.startswith('git push'):
        return {'risk': 'high', 'requires_approval': True, 'blocked': False, 'reason': 'github_push_requires_approval'}
    if lowered.startswith('git clone'):
        unsafe_target = any(token.startswith(('/', '~')) for token in tokens[2:] if not token.startswith('http'))
        risk = 'medium' if unsafe_target and not workspace else 'low'
        return {'risk': risk, 'requires_approval': risk != 'low', 'blocked': False, 'reason': 'git_clone_safe_workspace' if risk == 'low' else 'git_clone_absolute_target'}
    if lowered in LOW_RISK_COMMANDS or any(lowered.startswith(cmd + ' ') for cmd in LOW_RISK_COMMANDS):
        return {'risk': 'low', 'requires_approval': False, 'blocked': False, 'reason': 'read_only_shell_command'}
    if first_two in MEDIUM_RISK_COMMANDS or any(lowered.startswith(cmd + ' ') for cmd in MEDIUM_RISK_COMMANDS):
        return {'risk': 'medium', 'requires_approval': True, 'blocked': False, 'reason': 'dependency_or_branch_change'}
    if any(marker in lowered for marker in ['>', '>>', ' tee ', ' cp ', ' mkdir ', ' touch ']):
        return {'risk': 'medium', 'requires_approval': True, 'blocked': False, 'reason': 'shell_command_may_write_files'}
    return {'risk': 'medium', 'requires_approval': True, 'blocked': False, 'reason': 'unclassified_shell_command_requires_review'}


def _max_risk(left: str, right: str) -> str:
    return left if RISK_ORDER.get(left, 4) >= RISK_ORDER.get(right, 4) else right


def step_risk(step, task_type: str | None = None) -> dict:
    if step.safety_level == 'BLOCKED':
        return {'decision': 'blocked', 'risk': 'blocked', 'reason': 'step_marked_blocked'}

    tool_spec = get_tool_spec(step.action_type)
    registry_risk = tool_spec['risk_level'] if tool_spec else 'blocked'
    registry_requires_approval = bool(tool_spec and tool_spec.get('requires_approval'))
    reason = 'tool_registry_policy'

    if step.action_type == 'CODE_RUN' and (step.args or {}).get('kind') == 'shell':
        shell = classify_shell_command((step.args or {}).get('command', ''), workspace=(step.args or {}).get('workspace'))
        registry_risk = shell['risk']
        registry_requires_approval = shell['requires_approval']
        reason = shell['reason']

    if step.action_type in {'OS_PASTE', 'ASSIST_PASTE_BACK', 'WEB_TYPE', 'WEB_UPLOAD'}:
        registry_requires_approval = True
        registry_risk = _max_risk(registry_risk, 'high')
        reason = f'{step.action_type.lower()}_requires_approval'

    if step.action_type in {'PROFILE_EXPORT', 'PROFILE_IMPORT'}:
        registry_requires_approval = True
        registry_risk = _max_risk(registry_risk, 'high')
        reason = 'profile_memory_transfer_requires_approval'

    url = (step.args or {}).get('url')
    domain = urlparse(url).netloc if url else None
    if step.action_type in {'OS_OPEN_URL', 'WEB_NAVIGATE'} and domain not in LOCAL_DOMAINS and str(task_type or '').startswith('workflow'):
        registry_requires_approval = True
        registry_risk = _max_risk(registry_risk, 'medium')
        reason = 'external_url_requires_approval'
    safety_hints = query_relevant_memory(task_type=task_type, domain=domain, action_key=step.action_type)
    learned_confirm = any(item.get('policy') == 'require_confirmation' for item in safety_hints['safety'])
    learned_block = any(item.get('policy') == 'blocked' for item in safety_hints['safety'])

    if learned_block or registry_risk == 'blocked':
        return {'decision': 'blocked', 'risk': 'blocked', 'reason': 'learned_or_registry_block'}
    if (
        step.safety_level == 'CONFIRM'
        or registry_requires_approval
        or registry_risk == 'critical'
        or requires_confirmation(step.name)
        or learned_confirm
    ):
        return {'decision': 'confirm', 'risk': registry_risk, 'reason': reason, 'redacted_args': redact_text(str(step.args or {}), limit=600)}
    return {'decision': 'allow', 'risk': registry_risk, 'reason': reason}


def guard_step(step, task_type: str | None = None) -> str:
    return step_risk(step, task_type=task_type)['decision']
