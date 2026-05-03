from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from .state import db_conn
from .privacy import detect_secret, detect_sensitive, redact_text, redact_value, sensitivity_labels
from llm.embeddings import embed


def _now() -> str:
    return datetime.now(UTC).isoformat()


ALLOWED_SCOPES = {'personal', 'work', 'company', 'session', 'device'}
ALLOWED_KINDS = {'preference', 'workflow', 'fact', 'person', 'project', 'failure', 'fix', 'safety', 'context', 'summary', 'note', 'execution'}
SENSITIVE_MARKERS = {'api_key', 'password', 'secret', 'token', 'private key', 'ssn', 'credit card'}
LOW_VALUE_VALUES = {'ok', 'done', 'success', 'failure', 'none', 'null', 'n/a', ''}


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
    data['provenance'] = _loads(data.pop('provenance_json', None), {})
    data['pinned'] = bool(data.get('pinned'))
    data['archived'] = bool(data.get('archived'))
    return data


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except Exception:
        return None


def _quality_score(kind: str, key: str, value: str, *, confidence: float, source: str, permission: str) -> tuple[bool, list[str], float]:
    reasons: list[str] = []
    clean_value = ' '.join((value or '').split())
    lower = clean_value.lower()
    if kind not in ALLOWED_KINDS:
        reasons.append('unknown_kind')
    if not key.strip():
        reasons.append('missing_key')
    if len(clean_value) < 4 or lower in LOW_VALUE_VALUES:
        reasons.append('low_information_value')
    combined = f'{key}\n{clean_value}'
    if detect_secret(combined):
        reasons.append('secret_never_stored')
    elif (detect_sensitive(combined) or any(marker in lower or marker in key.lower() for marker in SENSITIVE_MARKERS)) and permission not in {'private', 'sensitive'}:
        reasons.append('sensitive_requires_private_permission')
    if source == 'auto' and confidence < 0.35:
        reasons.append('low_confidence_auto_memory')
    score = max(0.0, min(1.0, confidence))
    if len(clean_value) >= 24:
        score += 0.08
    if source in {'user', 'manual'}:
        score += 0.12
    if permission in {'private', 'sensitive'}:
        score += 0.04
    if reasons:
        score -= 0.2 * len(reasons)
    return not reasons, reasons, round(max(0.0, min(score, 1.0)), 3)


def _score(query: str, item: dict[str, Any], *, scope: str | None = None, task_type: str | None = None, permission: str | None = None) -> float:
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
    confidence_score = float(item.get('confidence') or 0.0) * 0.5
    usage_score = min(int(item.get('usage_count') or 0), 12) * 0.08
    updated = _parse_dt(item.get('last_used_at') or item.get('updated_at') or item.get('created_at'))
    age_days = (datetime.now(UTC) - updated).days if updated else 365
    recency_score = max(0.0, 0.45 - (age_days / 365))
    scope_score = 0.35 if scope and item.get('scope') == scope else 0.0
    permission_score = 0.25 if permission and item.get('permission') == permission else 0.0
    metadata = item.get('metadata') or {}
    task_score = 0.35 if task_type and (metadata.get('task_type') == task_type or task_type in (item.get('tags') or [])) else 0.0
    return text_score + token_score + semantic_score + pin_score + confidence_score + usage_score + recency_score + scope_score + permission_score + task_score


def _similar_existing(*, kind: str, key: str, value: str, scope: str) -> dict[str, Any] | None:
    normalized = ' '.join(value.lower().split())
    candidates = list_memory_items(kind=kind, scope=scope, include_archived=False, limit=100)
    for item in candidates:
        same_key = item.get('memory_key') == key
        same_value = ' '.join((item.get('value') or '').lower().split()) == normalized
        if same_key and same_value:
            return item
    return None


def reinforce_memory_item(memory_id: str, *, evidence: str | None = None, confidence_delta: float = 0.06, source: str | None = None) -> dict[str, Any] | None:
    item = get_memory_item(memory_id)
    if not item:
        return None
    metadata = {**(item.get('metadata') or {})}
    evidence_log = list(metadata.get('reinforcement_evidence') or [])
    if evidence:
        evidence_log.append({'at': _now(), 'evidence': evidence})
    metadata['reinforcement_evidence'] = evidence_log[-8:]
    return update_memory_item(
        memory_id,
        confidence=min(1.0, float(item.get('confidence') or 0.0) + confidence_delta),
        usage_count=int(item.get('usage_count') or 0) + 1,
        last_used_at=_now(),
        source=source or item.get('source'),
        metadata=metadata,
    )


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
    provenance: dict[str, Any] | None = None,
    user_notes: str = '',
    memory_id: str | None = None,
) -> dict[str, Any]:
    kind = kind if kind in ALLOWED_KINDS else 'note'
    scope = scope if scope in ALLOWED_SCOPES else 'personal'
    labels = sensitivity_labels(f'{key}\n{value}')
    ok_to_store, reasons, adjusted_confidence = _quality_score(kind, key, value, confidence=confidence, source=source, permission=permission)
    if not ok_to_store:
        return {
            'stored': False,
            'rejected': True,
            'reasons': reasons,
            'kind': kind,
            'scope': scope,
            'memory_key': key,
            'confidence': adjusted_confidence,
            'sensitivity': labels,
        }
    duplicate = _similar_existing(kind=kind, key=key, value=value, scope=scope)
    if duplicate:
        reinforced = reinforce_memory_item(duplicate['memory_id'], evidence=f'duplicate:{source}', confidence_delta=0.05, source=source)
        return {**(reinforced or duplicate), 'stored': True, 'merged': True}

    mid = memory_id or f'mem_{uuid.uuid4().hex}'
    now = _now()
    metadata = redact_value({**(metadata or {}), 'quality_score': adjusted_confidence, 'sensitivity': labels})
    provenance = redact_value(provenance or {'source': source, 'created_at': now})
    value = redact_text(value)
    payload = (
        mid,
        scope,
        kind,
        key,
        value,
        json.dumps(tags or [], sort_keys=True),
        adjusted_confidence,
        source,
        permission,
        1 if pinned else 0,
        0,
        json.dumps(provenance, sort_keys=True),
        user_notes,
        None,
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
              permission, pinned, archived, provenance_json, user_notes, last_used_at, usage_count, metadata_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            payload,
        )
    return {**(get_memory_item(mid) or {'memory_id': mid}), 'stored': True, 'merged': False}


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
    task_type: str | None = None,
    permission: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    candidates = list_memory_items(kind=kind, scope=scope, include_archived=False, limit=max(limit * 5, 50))
    if permission:
        candidates = [item for item in candidates if item.get('permission') in {permission, 'private'}]
    ranked = sorted(candidates, key=lambda item: _score(query, item, scope=scope, task_type=task_type, permission=permission), reverse=True)
    selected = [dict(item, score=round(_score(query, item, scope=scope, task_type=task_type, permission=permission), 4)) for item in ranked[:limit]]
    with db_conn() as conn:
        for item in selected:
            conn.execute(
                'UPDATE memory_items SET usage_count=COALESCE(usage_count,0)+1, last_used_at=? WHERE memory_id=?',
                (_now(), item['memory_id']),
            )
    return selected


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
        'user_notes',
        'last_used_at',
        'usage_count',
        'updated_at',
    }
    fields = []
    params: list[Any] = []
    if changes.get('value') is not None and detect_secret(str(changes.get('value'))):
        return None
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
        if key == 'provenance':
            fields.append('provenance_json=?')
            params.append(json.dumps(value or {}, sort_keys=True))
            continue
        if key in {'pinned', 'archived'}:
            fields.append(f'{key}=?')
            params.append(1 if value else 0)
            continue
        if key in allowed:
            if key == 'value':
                value = redact_text(str(value))
            fields.append(f'{key}=?')
            params.append(value)
    if not fields:
        return get_memory_item(memory_id)
    if 'updated_at' not in changes:
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


def merge_duplicate_memories() -> dict[str, Any]:
    items = list_memory_items(include_archived=False, limit=10000)
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        key = (item.get('scope') or '', item.get('kind') or '', item.get('memory_key') or '', ' '.join((item.get('value') or '').lower().split()))
        groups[key].append(item)
    merged = []
    for _, group in groups.items():
        if len(group) < 2:
            continue
        keeper = max(group, key=lambda item: (item.get('pinned'), float(item.get('confidence') or 0), int(item.get('usage_count') or 0)))
        confidence = min(1.0, max(float(item.get('confidence') or 0) for item in group) + 0.04 * (len(group) - 1))
        usage_count = sum(int(item.get('usage_count') or 0) for item in group)
        provenance = {**(keeper.get('provenance') or {}), 'merged_from': [item['memory_id'] for item in group if item['memory_id'] != keeper['memory_id']]}
        update_memory_item(keeper['memory_id'], confidence=confidence, usage_count=usage_count, provenance=provenance)
        for item in group:
            if item['memory_id'] != keeper['memory_id']:
                archive_memory_item(item['memory_id'])
        merged.append({'keeper': keeper['memory_id'], 'archived': provenance['merged_from']})
    return {'merged_groups': len(merged), 'items': merged}


def compact_memory_items(*, scope: str | None = None, kind: str | None = None, older_than_days: int = 30, limit: int = 200) -> dict[str, Any]:
    merge_result = merge_duplicate_memories()
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    candidates = [
        item for item in list_memory_items(kind=kind, scope=scope, include_archived=False, limit=limit)
        if not item.get('pinned') and (_parse_dt(item.get('updated_at')) or datetime.min.replace(tzinfo=UTC)) <= cutoff
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        grouped[(item.get('scope') or 'personal', item.get('kind') or 'note')].append(item)
    summaries = []
    for (group_scope, group_kind), group in grouped.items():
        if len(group) < 2:
            continue
        top = sorted(group, key=lambda item: (int(item.get('usage_count') or 0), float(item.get('confidence') or 0)), reverse=True)[:8]
        summary_value = '; '.join(f"{item.get('memory_key')}: {item.get('value')}" for item in top)
        summary = remember_item(
            kind='summary',
            key=f'{group_kind}_summary',
            value=summary_value[:1800],
            scope=group_scope,
            permission='private',
            tags=['compacted', group_kind],
            confidence=min(0.9, sum(float(item.get('confidence') or 0) for item in top) / len(top) + 0.05),
            source='compaction',
            metadata={'compacted_kind': group_kind, 'raw_count': len(group), 'raw_memory_ids': [item['memory_id'] for item in group]},
            provenance={'raw_memory_ids': [item['memory_id'] for item in group], 'compacted_at': _now()},
        )
        for item in group:
            archive_memory_item(item['memory_id'])
        summaries.append(summary)
    return {'ok': True, 'merge': merge_result, 'summaries_created': len(summaries), 'summaries': summaries}


def memory_lifecycle_sweep(*, stale_after_days: int = 180, low_confidence: float = 0.25) -> dict[str, Any]:
    now = datetime.now(UTC)
    archived = []
    decayed = []
    for item in list_memory_items(include_archived=False, limit=10000):
        if item.get('pinned') or item.get('kind') == 'safety':
            continue
        updated = _parse_dt(item.get('last_used_at') or item.get('updated_at') or item.get('created_at')) or now
        age_days = (now - updated).days
        confidence = float(item.get('confidence') or 0.0)
        if age_days >= stale_after_days and confidence <= low_confidence:
            archive_memory_item(item['memory_id'])
            archived.append(item['memory_id'])
        elif age_days >= 60 and confidence > low_confidence:
            new_confidence = max(low_confidence, confidence - 0.04)
            update_memory_item(item['memory_id'], confidence=new_confidence)
            decayed.append(item['memory_id'])
    return {'archived': archived, 'decayed': decayed}
