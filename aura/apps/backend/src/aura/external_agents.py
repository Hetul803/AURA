from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .state import db_conn

PROFILE_KEY = 'external_agent_mediation'

DEFAULT_AGENTS = [
    {
        'agent_id': 'victor-slack',
        'name': 'Victor',
        'platform': 'Slack',
        'scope': 'work',
        'trust_level': 'not_connected',
        'allowed_actions': ['summarize_interaction', 'prepare_reply_for_approval'],
        'approval_requirements': ['before_sending', 'before_sharing_memory', 'before_cross_identity_context'],
        'last_interaction': None,
        'notes': 'Future connector. AURA will mediate interactions with enterprise agents after user approval.',
        'connected': False,
    }
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _loads(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return DEFAULT_AGENTS
    try:
        data = json.loads(value)
        return data if isinstance(data, list) else DEFAULT_AGENTS
    except Exception:
        return DEFAULT_AGENTS


def _save(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with db_conn() as conn:
        conn.execute(
            'INSERT INTO profile_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (PROFILE_KEY, json.dumps(items, sort_keys=True)),
        )
    return items


def list_external_agents() -> list[dict[str, Any]]:
    row = db_conn().execute('SELECT value FROM profile_meta WHERE key=?', (PROFILE_KEY,)).fetchone()
    return _loads(row['value'] if row else None)


def upsert_external_agent(agent: dict[str, Any]) -> dict[str, Any]:
    items = list_external_agents()
    agent_id = agent.get('agent_id') or f"{str(agent.get('name') or 'agent').lower().replace(' ', '-')}-{str(agent.get('platform') or 'local').lower()}"
    payload = {
        'agent_id': agent_id,
        'name': agent.get('name') or 'External Agent',
        'platform': agent.get('platform') or 'unknown',
        'scope': agent.get('scope') or 'session',
        'trust_level': agent.get('trust_level') or 'not_connected',
        'allowed_actions': agent.get('allowed_actions') or [],
        'approval_requirements': agent.get('approval_requirements') or ['before_action'],
        'last_interaction': agent.get('last_interaction'),
        'notes': agent.get('notes') or '',
        'connected': bool(agent.get('connected')),
        'updated_at': _now(),
    }
    next_items = [item for item in items if item.get('agent_id') != agent_id]
    next_items.append(payload)
    _save(next_items)
    return payload


def external_agent_status() -> dict[str, Any]:
    agents = list_external_agents()
    return {
        'connected_count': len([item for item in agents if item.get('connected')]),
        'configured_count': len(agents),
        'agents': agents,
        'honest_scope': 'External agent mediation is a local configuration foundation. No Slack or enterprise agent connector is active yet.',
    }
