from __future__ import annotations
from .state import db_conn
from llm.embeddings import embed


def write_memory(key: str, value: str, tags: list[str] | None = None, importance: int = 1, pinned: int = 0):
    with db_conn() as conn:
        conn.execute(
            'INSERT INTO memories(key,value,tags,importance,pinned) VALUES(?,?,?,?,?)',
            (key, value, ','.join(tags or []), importance, pinned),
        )


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


def update_memory(mid: int, value: str | None = None, pinned: int | None = None):
    conn = db_conn()
    row = conn.execute('SELECT * FROM memories WHERE id=?', (mid,)).fetchone()
    if not row:
        return False
    value = value if value is not None else row['value']
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
