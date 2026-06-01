from __future__ import annotations

import json

from .privacy import detect_secret, redact_text
from .state import db_conn
from llm.embeddings import embed



def write_memory(key: str, value: str, tags: list[str] | None = None, importance: int = 1, pinned: int = 0):
    if detect_secret(f'{key}\n{value}'):
        return {'stored': False, 'rejected': True, 'reasons': ['secret_never_stored'], 'key': key}
    value = redact_text(value)
    with db_conn() as conn:
        conn.execute(
            'INSERT INTO memories(key,value,tags,importance,pinned) VALUES(?,?,?,?,?)',
            (key, value, ','.join(tags or []), importance, pinned),
        )
    try:
        from .memory_engine import remember_item

        remember_item(
            kind=(tags or ['legacy'])[0],
            key=key,
            value=value,
            tags=tags or [],
            confidence=min(1.0, max(0.1, importance / 5)),
            source='legacy_memory',
            pinned=bool(pinned),
            metadata={'legacy_key': key, 'legacy_importance': importance},
        )
    except Exception:
        pass



def list_memories(q: str | None = None):
    conn = db_conn()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            'SELECT * FROM memories WHERE key LIKE ? OR value LIKE ? OR tags LIKE ? ORDER BY pinned DESC, importance DESC, id DESC',
            (like, like, like),
        ).fetchall()
    else:
        rows = conn.execute('SELECT * FROM memories ORDER BY pinned DESC, importance DESC, id DESC').fetchall()
    return [dict(r) for r in rows]



def latest_memory(key_prefix: str) -> dict | None:
    row = db_conn().execute(
        'SELECT * FROM memories WHERE key LIKE ? ORDER BY pinned DESC, importance DESC, id DESC LIMIT 1',
        (f'{key_prefix}%',),
    ).fetchone()
    return dict(row) if row else None



def execution_hints(scope: str, limit: int = 5) -> list[dict]:
    like = f'%{scope}%'
    rows = db_conn().execute(
        'SELECT * FROM memories WHERE key LIKE ? OR tags LIKE ? ORDER BY pinned DESC, importance DESC, id DESC LIMIT ?',
        (like, '%execution%', limit),
    ).fetchall()
    return [dict(r) for r in rows]



def latest_execution_memory(scope: str, outcome: str | None = None) -> dict | None:
    key = f'exec:{scope}:'
    if outcome:
        key += outcome
    return latest_memory(key)



def remember_execution(scope: str, outcome: str, detail: str, *, tags: list[str] | None = None, importance: int = 4, metadata: dict | None = None):
    merged_tags = ['execution', *(tags or [])]
    value = json.dumps({'detail': detail, 'metadata': metadata or {}}, sort_keys=True)
    write_memory(f'exec:{scope}:{outcome}', value, tags=merged_tags, importance=importance)



def update_memory(mid: int, value: str | None = None, pinned: int | None = None):
    conn = db_conn()
    row = conn.execute('SELECT * FROM memories WHERE id=?', (mid,)).fetchone()
    if not row:
        return False
    if value is not None and detect_secret(value):
        return False
    value = redact_text(value) if value is not None else row['value']
    pinned = pinned if pinned is not None else row['pinned']
    with conn:
        conn.execute('UPDATE memories SET value=?, pinned=? WHERE id=?', (value, pinned, mid))
    return True



def delete_memory(mid: int):
    with db_conn() as conn:
        conn.execute('DELETE FROM memories WHERE id=?', (mid,))



def semantic_rank(query: str, items: list[dict]) -> list[dict]:
    qv = embed(query)[0]
    return sorted(items, key=lambda x: abs(embed(x['value'])[0] - qv))
