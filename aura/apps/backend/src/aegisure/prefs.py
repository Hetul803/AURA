from __future__ import annotations
from datetime import datetime
from .state import db_conn

SUPPRESS_THRESHOLD = 0.72


def _update_conf(old: float, hit: bool) -> float:
    # frequency+recency-ish weighted update
    base = old * 0.75
    boost = 0.25 if hit else -0.1
    return max(0.0, min(1.0, base + boost))


def set_pref(key: str, value: str, hit: bool = True):
    conn = db_conn()
    row = conn.execute('SELECT confidence FROM preferences WHERE decision_key=?', (key,)).fetchone()
    c = _update_conf(row['confidence'], hit) if row else 0.78
    with conn:
        conn.execute(
            'INSERT INTO preferences(decision_key,value,confidence,updated_at) VALUES(?,?,?,?) '
            'ON CONFLICT(decision_key) DO UPDATE SET value=excluded.value, confidence=?, updated_at=excluded.updated_at',
            (key, value, c, datetime.utcnow().isoformat(), c),
        )


def should_ask(key: str) -> bool:
    row = db_conn().execute('SELECT confidence FROM preferences WHERE decision_key=?', (key,)).fetchone()
    return (not row) or row['confidence'] < SUPPRESS_THRESHOLD


def get_pref_value(key: str) -> str | None:
    row = db_conn().execute('SELECT value FROM preferences WHERE decision_key=?', (key,)).fetchone()
    return row['value'] if row else None


def get_prefs():
    return [dict(r) for r in db_conn().execute('SELECT decision_key,value,confidence,updated_at FROM preferences ORDER BY decision_key').fetchall()]


def reset_pref(key: str):
    with db_conn() as conn:
        conn.execute('DELETE FROM preferences WHERE decision_key=?', (key,))


def reset_all():
    with db_conn() as conn:
        conn.execute('DELETE FROM preferences')
