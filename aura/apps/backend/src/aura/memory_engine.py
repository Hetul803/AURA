from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .state import db_conn
from llm.embeddings import embed


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _row_to_memory(row) -> dict[str, Any]:
    data = dict(row)
    data['tags'] = _loads(data.pop('tags_json', None), [])
    data['metadata'] = _loads(data.pop('metadata_json', None), {})
    data['pinned'] = bool(data.get('pinned'))
    data['archived'] = bool(data.get('archived'))
    return data


def _score(query: str, item: dict[str, Any]) -> float:
    haystack = ' '.join([
        item.get('memory_key') or '',
        item.get('value') or '',
        ' '.join(item.get('tags') or []),
        item.get('kind') or '',
        item.get('scope') or '',
    ]).lower()
    q = query.lower().strip()
    text_score = 2.0 if q and q in haystack else 0.0
    token_score = sum(0.25 for token in q.split() if token and token in haystack)
    semantic_distance = abs(embed(query)[0] - embed(haystack)[0]) if q else 0.0
    semantic_score = max(0.0, 1.0 - semantic_distance)
    pin_score = 0.25 if item.get('pinned') else 0.0
    confidence_score = float(item.get('confidence') or 0.0) * 0.2
    return text_score + token_score + semantic_score + pin_score + confidence_score


def remember_item(
    *,
    kind: str,
    key: str,
    value: str,
    scope: str = 'personal',
    permission: str = 'private',
    tags: list[str] | None = None,
    confidence: float = 0.5,
    source: str = 'manual',
    pinned: bool = False,
    metadata: dict[str, Any] | None = None,
    memory_id: str | None = None,
) -> dict[str, Any]:
    mid = memory_id or f'mem_{uuid.uuid4().hex}'
    now = _now()
    payload = (
        mid,
        scope,
        kind,
        key,
        value,
        json.dumps(tags or [], sort_keys=True),
        confidence,
        source,
        permission,
        1 if pinned else 0,
        0,
        json.dumps(metadata or {}, sort_keys=True),
        now,
        now,
    )
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO memory_items(
              memory_id, scope, kind, memory_key, value, tags_json, confidence, source,
              permission, pinned, archived, metadata_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            payload,
        )
    return get_memory_item(mid) or {'memory_id': mid}


def get_memory_item(memory_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM memory_items WHERE memory_id=?', (memory_id,)).fetchone()
    return _row_to_memory(row) if row else None


def list_memory_items(
    q: str | None = None,
    *,
    kind: str | None = None,
    scope: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if not include_archived:
        clauses.append('archived=0')
    if kind:
        clauses.append('kind=?')
        params.append(kind)
    if scope:
        clauses.append('scope=?')
        params.append(scope)
    if q:
        clauses.append('(memory_key LIKE ? OR value LIKE ? OR tags_json LIKE ? OR kind LIKE ?)')
        like = f'%{q}%'
        params.extend([like, like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = db_conn().execute(
        f'''
        SELECT * FROM memory_items
        {where}
        ORDER BY pinned DESC, confidence DESC, updated_at DESC
        LIMIT ?
        ''',
        [*params, limit],
    ).fetchall()
    return [_row_to_memory(row) for row in rows]


def search_memory_items(
    query: str,
    *,
    kind: str | None = None,
    scope: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    candidates = list_memory_items(kind=kind, scope=scope, include_archived=False, limit=max(limit * 5, 50))
    ranked = sorted(candidates, key=lambda item: _score(query, item), reverse=True)
    return [dict(item, score=round(_score(query, item), 4)) for item in ranked[:limit]]


def update_memory_item(memory_id: str, **changes: Any) -> dict[str, Any] | None:
    allowed = {
        'scope',
        'kind',
        'memory_key',
        'value',
        'confidence',
        'source',
        'permission',
        'pinned',
        'archived',
    }
    fields = []
    params: list[Any] = []
    for key, value in changes.items():
        if value is None:
            continue
        if key == 'key':
            key = 'memory_key'
        if key == 'tags':
            fields.append('tags_json=?')
            params.append(json.dumps(value or [], sort_keys=True))
            continue
        if key == 'metadata':
            fields.append('metadata_json=?')
            params.append(json.dumps(value or {}, sort_keys=True))
            continue
        if key in {'pinned', 'archived'}:
            fields.append(f'{key}=?')
            params.append(1 if value else 0)
            continue
        if key in allowed:
            fields.append(f'{key}=?')
            params.append(value)
    if not fields:
        return get_memory_item(memory_id)
    fields.append('updated_at=?')
    params.append(_now())
    params.append(memory_id)
    with db_conn() as conn:
        cur = conn.execute(f"UPDATE memory_items SET {', '.join(fields)} WHERE memory_id=?", params)
        if cur.rowcount == 0:
            return None
    return get_memory_item(memory_id)


def archive_memory_item(memory_id: str) -> bool:
    return update_memory_item(memory_id, archived=True) is not None


def delete_memory_item(memory_id: str) -> bool:
    with db_conn() as conn:
        cur = conn.execute('DELETE FROM memory_items WHERE memory_id=?', (memory_id,))
        return cur.rowcount > 0
