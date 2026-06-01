from __future__ import annotations

import fnmatch
import json
import re
from typing import Any
from urllib.parse import urlparse

from .privacy import detect_secret
from .state import db_conn

PROFILE_KEY = 'guardian_policy'

DEFAULT_POLICY = {
    'mode': 'balanced',
    'trusted_domains': [],
    'trusted_folders': [],
    'trusted_workflows': [],
    'trusted_command_patterns': [],
    'blocked_command_patterns': [],
    'notes': 'Guardian protects Aegisure-managed actions today. Ambient OS-wide protection is planned.',
}

STRICT_APPROVAL_ACTIONS = {
    'CODE_RUN',
    'OS_PASTE',
    'ASSIST_PASTE_BACK',
    'WEB_TYPE',
    'WEB_UPLOAD',
    'FS_WRITE_TEXT',
    'PROFILE_EXPORT',
    'PROFILE_IMPORT',
    'OS_OPEN_URL',
    'WEB_NAVIGATE',
}


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _save_policy(policy: dict[str, Any]) -> dict[str, Any]:
    with db_conn() as conn:
        conn.execute(
            'INSERT INTO profile_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (PROFILE_KEY, json.dumps(policy, sort_keys=True)),
        )
    return policy


def guardian_policy() -> dict[str, Any]:
    row = db_conn().execute('SELECT value FROM profile_meta WHERE key=?', (PROFILE_KEY,)).fetchone()
    policy = {**DEFAULT_POLICY, **_loads(row['value'] if row else None)}
    mode = str(policy.get('mode') or 'balanced').lower()
    if mode not in {'relaxed', 'balanced', 'strict'}:
        mode = 'balanced'
    policy['mode'] = mode
    for key in ['trusted_domains', 'trusted_folders', 'trusted_workflows', 'trusted_command_patterns', 'blocked_command_patterns']:
        policy[key] = [str(item) for item in (policy.get(key) or []) if str(item).strip()]
    return policy


def update_guardian_policy(patch: dict[str, Any]) -> dict[str, Any]:
    policy = guardian_policy()
    for key in DEFAULT_POLICY:
        if key in patch and patch[key] is not None:
            policy[key] = patch[key]
    return _save_policy(guardian_policy_normalized(policy))


def guardian_policy_normalized(policy: dict[str, Any]) -> dict[str, Any]:
    merged = {**DEFAULT_POLICY, **(policy or {})}
    mode = str(merged.get('mode') or 'balanced').lower()
    merged['mode'] = mode if mode in {'relaxed', 'balanced', 'strict'} else 'balanced'
    for key in ['trusted_domains', 'trusted_folders', 'trusted_workflows', 'trusted_command_patterns', 'blocked_command_patterns']:
        merged[key] = sorted({str(item).strip() for item in (merged.get(key) or []) if str(item).strip()})
    return merged


def _match_pattern(value: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        try:
            if re.search(pattern, value, re.IGNORECASE):
                return pattern
        except re.error:
            if fnmatch.fnmatch(value.lower(), pattern.lower()):
                return pattern
    return None


def _domain(url: str | None) -> str:
    if not url:
        return ''
    return urlparse(url).netloc.lower()


def apply_guardian_policy(step, decision: dict[str, Any], *, task_type: str | None = None) -> dict[str, Any]:
    policy = guardian_policy()
    action = getattr(step, 'action_type', '')
    args = getattr(step, 'args', {}) or {}
    command = str(args.get('command') or '')
    url = str(args.get('url') or '')
    path = str(args.get('path') or args.get('workspace') or '')
    domain = _domain(url)

    blocked_pattern = _match_pattern(command, policy.get('blocked_command_patterns') or [])
    if blocked_pattern:
        return {
            **decision,
            'decision': 'blocked',
            'risk': 'blocked',
            'reason': 'guardian_blocked_command_pattern',
            'policy_pattern': blocked_pattern,
        }

    if command and detect_secret(command):
        return {**decision, 'decision': 'blocked', 'risk': 'blocked', 'reason': 'command_contains_secret'}

    trusted_command = _match_pattern(command, policy.get('trusted_command_patterns') or [])
    if trusted_command and decision.get('decision') == 'confirm' and decision.get('risk') in {'low', 'medium'}:
        return {**decision, 'decision': 'allow', 'reason': 'trusted_command_pattern', 'policy_pattern': trusted_command}

    if domain and domain in {item.lower() for item in policy.get('trusted_domains') or []} and decision.get('risk') == 'medium':
        return {**decision, 'decision': 'allow', 'reason': 'trusted_domain'}

    if path and any(path.startswith(folder) for folder in policy.get('trusted_folders') or []) and action == 'FS_WRITE_TEXT' and decision.get('risk') == 'medium':
        return {**decision, 'decision': 'allow', 'reason': 'trusted_folder'}

    mode = policy.get('mode') or 'balanced'
    if mode == 'strict' and action in STRICT_APPROVAL_ACTIONS and decision.get('decision') == 'allow':
        return {
            **decision,
            'decision': 'confirm',
            'risk': 'medium' if decision.get('risk') == 'low' else decision.get('risk', 'medium'),
            'reason': 'guardian_strict_mode_requires_approval',
        }

    try:
        from .identity_boundary import get_active_identity

        identity = get_active_identity()
        if identity.get('identity_id') == 'company' and action in STRICT_APPROVAL_ACTIONS and decision.get('decision') == 'allow':
            return {**decision, 'decision': 'confirm', 'risk': 'medium', 'reason': 'company_identity_strict_by_default'}
        if identity.get('identity_id') == 'session' and action in {'FS_WRITE_TEXT', 'PROFILE_EXPORT', 'PROFILE_IMPORT'} and decision.get('decision') == 'allow':
            return {**decision, 'decision': 'confirm', 'risk': 'medium', 'reason': 'session_identity_ephemeral_requires_confirmation'}
    except Exception:
        pass

    return decision
