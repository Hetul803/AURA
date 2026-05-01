from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .state import db_conn


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


def ensure_default_identities() -> None:
    if list_identities():
        return
    create_identity(
        identity_id='personal',
        name='Personal AURA',
        identity_type='personal',
        owner='user',
        memory_scope='personal',
        policy_scope='personal',
        metadata={'default': True},
    )
    create_identity(
        identity_id='company',
        name='Company AURA',
        identity_type='company',
        owner='organization',
        memory_scope='company',
        policy_scope='enterprise',
        metadata={'default': True, 'status': 'planned'},
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
        source_identity='personal',
        target_identity='company',
        data_class='personal_private',
        action='share',
        decision='require_approval',
        reason='Personal data requires explicit approval before work/company sharing.',
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
            (iid, name, identity_type, owner, memory_scope, policy_scope, json.dumps(metadata or {}, sort_keys=True), now, now),
        )
    return get_identity(iid) or {'identity_id': iid}


def get_identity(identity_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM aura_identities WHERE identity_id=?', (identity_id,)).fetchone()
    return _identity_row(row) if row else None


def list_identities() -> list[dict[str, Any]]:
    rows = db_conn().execute('SELECT * FROM aura_identities ORDER BY identity_type, name').fetchall()
    return [_identity_row(row) for row in rows]


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
