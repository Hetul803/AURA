from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .state import db_conn

DEFAULT_APPROVALS = [
    'send_email',
    'paste_external',
    'run_risky_shell',
    'delete_or_overwrite_files',
    'export_import_memory',
    'cross_identity_memory',
    'spend_money',
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _identity_row(row) -> dict[str, Any]:
    data = dict(row)
    data['metadata'] = _loads(data.pop('metadata_json', None))
    return data


def _policy_row(row) -> dict[str, Any]:
    data = dict(row)
    data['metadata'] = _loads(data.pop('metadata_json', None))
    return data


def _default_metadata(*, memory_scope: str, trust_level: str = 'user_owned') -> dict[str, Any]:
    allowed = [memory_scope]
    if memory_scope == 'personal':
        allowed.append('session')
    return {
        'trust_level': trust_level,
        'allowed_memory_scopes': allowed,
        'allowed_tool_scopes': ['desktop-local', 'browser-visible', 'filesystem', 'code'],
        'requires_approval_for': DEFAULT_APPROVALS,
        'local_first': True,
        'crypto_signing': 'planned_not_active',
    }


def _ensure_identity(
    *,
    identity_id: str,
    name: str,
    identity_type: str,
    owner: str,
    memory_scope: str,
    policy_scope: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = get_identity(identity_id)
    if existing:
        return existing
    return create_identity(
        identity_id=identity_id,
        name=name,
        identity_type=identity_type,
        owner=owner,
        memory_scope=memory_scope,
        policy_scope=policy_scope,
        metadata=metadata,
    )


def ensure_default_identities() -> None:
    _ensure_identity(
        identity_id='personal',
        name='Personal Aegisure',
        identity_type='personal',
        owner='user',
        memory_scope='personal',
        policy_scope='personal',
        metadata={**_default_metadata(memory_scope='personal'), 'default': True},
    )
    _ensure_identity(
        identity_id='work',
        name='Work Aegisure',
        identity_type='work',
        owner='user',
        memory_scope='work',
        policy_scope='work',
        metadata={**_default_metadata(memory_scope='work'), 'default': True},
    )
    _ensure_identity(
        identity_id='company',
        name='Company Aegisure',
        identity_type='company',
        owner='organization',
        memory_scope='company',
        policy_scope='enterprise',
        metadata={**_default_metadata(memory_scope='company', trust_level='organization_managed_planned'), 'default': True, 'status': 'planned'},
    )
    _ensure_identity(
        identity_id='session',
        name='Session / Guest Aegisure',
        identity_type='session',
        owner='user',
        memory_scope='session',
        policy_scope='session',
        metadata={**_default_metadata(memory_scope='session', trust_level='temporary'), 'default': True, 'ephemeral': True},
    )
    upsert_boundary_policy(
        source_identity='company',
        target_identity='personal',
        data_class='company_confidential',
        action='remember',
        decision='deny',
        reason='Company confidential data must not enter personal memory.',
    )
    upsert_boundary_policy(
        source_identity='work',
        target_identity='personal',
        data_class='personal_private',
        action='remember',
        decision='require_approval',
        reason='Personal memory should not automatically enter work Aegisure context.',
    )
    upsert_boundary_policy(
        source_identity='work',
        target_identity='personal',
        data_class='work_private',
        action='remember',
        decision='require_approval',
        reason='Work memory should not automatically enter personal Aegisure context.',
    )
    upsert_boundary_policy(
        source_identity='personal',
        target_identity='work',
        data_class='personal_private',
        action='remember',
        decision='require_approval',
        reason='Personal memory should not automatically enter work Aegisure context.',
    )
    upsert_boundary_policy(
        source_identity='personal',
        target_identity='company',
        data_class='personal_private',
        action='share',
        decision='require_approval',
        reason='Personal data requires explicit approval before work/company sharing.',
    )
    if not _profile_meta_get('active_identity_id'):
        _profile_meta_set('active_identity_id', 'personal')


def _profile_meta_get(key: str) -> str | None:
    row = db_conn().execute('SELECT value FROM profile_meta WHERE key=?', (key,)).fetchone()
    return row['value'] if row else None


def _profile_meta_set(key: str, value: str) -> None:
    with db_conn() as conn:
        conn.execute(
            'INSERT INTO profile_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (key, value),
        )


def create_identity(
    *,
    name: str,
    identity_type: str,
    owner: str,
    memory_scope: str,
    policy_scope: str,
    metadata: dict[str, Any] | None = None,
    identity_id: str | None = None,
) -> dict[str, Any]:
    iid = identity_id or f'id_{uuid.uuid4().hex}'
    now = _now()
    merged_metadata = {**_default_metadata(memory_scope=memory_scope), **(metadata or {})}
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO aura_identities(identity_id, name, identity_type, owner, memory_scope, policy_scope, metadata_json, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(identity_id) DO UPDATE SET
              name=excluded.name,
              identity_type=excluded.identity_type,
              owner=excluded.owner,
              memory_scope=excluded.memory_scope,
              policy_scope=excluded.policy_scope,
              metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at
            ''',
            (iid, name, identity_type, owner, memory_scope, policy_scope, json.dumps(merged_metadata, sort_keys=True), now, now),
        )
    return get_identity(iid) or {'identity_id': iid}


def get_identity(identity_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM aura_identities WHERE identity_id=?', (identity_id,)).fetchone()
    return _identity_row(row) if row else None


def list_identities() -> list[dict[str, Any]]:
    rows = db_conn().execute('SELECT * FROM aura_identities ORDER BY identity_type, name').fetchall()
    return [_identity_row(row) for row in rows]


def get_active_identity() -> dict[str, Any]:
    ensure_default_identities()
    identity_id = _profile_meta_get('active_identity_id') or 'personal'
    identity = get_identity(identity_id) or get_identity('personal')
    if not identity:
        create_identity(
            identity_id='personal',
            name='Personal Aegisure',
            identity_type='personal',
            owner='user',
            memory_scope='personal',
            policy_scope='personal',
            metadata={**_default_metadata(memory_scope='personal'), 'default': True},
        )
        identity = get_identity('personal')
    return identity or {'identity_id': 'personal', 'name': 'Personal Aegisure', 'memory_scope': 'personal', 'metadata': _default_metadata(memory_scope='personal')}


def set_active_identity(identity_id: str) -> dict[str, Any]:
    ensure_default_identities()
    identity = get_identity(identity_id)
    if not identity:
        raise KeyError(identity_id)
    _profile_meta_set('active_identity_id', identity_id)
    return identity


def allowed_memory_scopes(identity: dict[str, Any] | None = None) -> list[str]:
    identity = identity or get_active_identity()
    metadata = identity.get('metadata') or {}
    scopes = metadata.get('allowed_memory_scopes') or [identity.get('memory_scope') or 'personal']
    return [str(scope) for scope in scopes if scope]


def memory_scope_decision(*, requested_scope: str | None, action: str = 'remember', active_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = active_identity or get_active_identity()
    scope = requested_scope if requested_scope not in {None, '', 'active'} else identity.get('memory_scope') or 'personal'
    allowed = set(allowed_memory_scopes(identity))
    if scope in allowed:
        return {
            'decision': 'allow',
            'reason': 'scope_allowed_for_active_identity',
            'identity': identity,
            'scope': scope,
            'allowed_memory_scopes': sorted(allowed),
        }
    target_identity = next((item for item in list_identities() if item.get('memory_scope') == scope), None)
    boundary = check_boundary(
        source_identity=identity.get('identity_id') or 'personal',
        target_identity=(target_identity or {}).get('identity_id') or scope,
        data_class=f'{scope}_private',
        action=action,
    )
    return {
        **boundary,
        'identity': identity,
        'scope': scope,
        'allowed_memory_scopes': sorted(allowed),
        'reason': boundary.get('reason') or 'cross_identity_memory_requires_approval',
    }


def upsert_boundary_policy(
    *,
    source_identity: str,
    target_identity: str,
    data_class: str,
    action: str,
    decision: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
    policy_id: str | None = None,
) -> dict[str, Any]:
    pid = policy_id or f'policy_{source_identity}_{target_identity}_{data_class}_{action}'.replace(':', '_').replace(' ', '_')
    now = _now()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO boundary_policies(policy_id, source_identity, target_identity, data_class, action, decision, reason, metadata_json, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(policy_id) DO UPDATE SET
              source_identity=excluded.source_identity,
              target_identity=excluded.target_identity,
              data_class=excluded.data_class,
              action=excluded.action,
              decision=excluded.decision,
              reason=excluded.reason,
              metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at
            ''',
            (pid, source_identity, target_identity, data_class, action, decision, reason, json.dumps(metadata or {}, sort_keys=True), now, now),
        )
    return get_boundary_policy(pid) or {'policy_id': pid}


def get_boundary_policy(policy_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM boundary_policies WHERE policy_id=?', (policy_id,)).fetchone()
    return _policy_row(row) if row else None


def list_boundary_policies() -> list[dict[str, Any]]:
    rows = db_conn().execute('SELECT * FROM boundary_policies ORDER BY source_identity, target_identity, data_class, action').fetchall()
    return [_policy_row(row) for row in rows]


def check_boundary(
    *,
    source_identity: str,
    target_identity: str,
    data_class: str,
    action: str,
) -> dict[str, Any]:
    ensure_default_identities()
    rows = list_boundary_policies()
    for row in rows:
        source_match = row['source_identity'] in {source_identity, '*'}
        target_match = row['target_identity'] in {target_identity, '*'}
        data_match = row['data_class'] in {data_class, '*'}
        action_match = row['action'] in {action, '*'}
        if source_match and target_match and data_match and action_match:
            return {
                'decision': row['decision'],
                'reason': row['reason'],
                'policy': row,
                'source_identity': source_identity,
                'target_identity': target_identity,
                'data_class': data_class,
                'action': action,
            }
    if source_identity == target_identity:
        return {'decision': 'allow', 'reason': 'same_identity_boundary', 'policy': None, 'source_identity': source_identity, 'target_identity': target_identity, 'data_class': data_class, 'action': action}
    return {'decision': 'require_approval', 'reason': 'cross_identity_transfer_requires_explicit_approval', 'policy': None, 'source_identity': source_identity, 'target_identity': target_identity, 'data_class': data_class, 'action': action}
