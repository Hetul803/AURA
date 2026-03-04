from __future__ import annotations
import json, uuid
from datetime import datetime
from .state import db_conn


def _parameterize_steps(steps: list[dict], slots: dict[str, str] | None):
    slots = slots or {}
    out = json.dumps(steps)
    for k, v in slots.items():
        out = out.replace(str(v), '{' + k + '}')
    return out


def record_macro(name: str, trigger: str, steps: list[dict], slots: dict[str, str] | None = None):
    mid = str(uuid.uuid4())
    with db_conn() as conn:
        conn.execute(
            'INSERT INTO macros(id,name,trigger_signature,steps_template,success_count,last_used) VALUES(?,?,?,?,?,?)',
            (mid, name, trigger, _parameterize_steps(steps, slots), 1, datetime.utcnow().isoformat()),
        )
    return mid


def list_macros():
    return [dict(r) for r in db_conn().execute('SELECT * FROM macros ORDER BY success_count DESC, last_used DESC').fetchall()]


def match_macro(signature: str):
    for m in list_macros():
        if m['enabled'] and m['trigger_signature'] == signature:
            return m
    return None


def render_macro_steps(macro: dict, slots: dict[str, str] | None = None):
    tpl = macro['steps_template']
    for k, v in (slots or {}).items():
        tpl = tpl.replace('{' + k + '}', str(v))
    return json.loads(tpl)


def touch_macro(macro_id: str):
    with db_conn() as conn:
        conn.execute(
            'UPDATE macros SET success_count = success_count + 1, last_used=? WHERE id=?',
            (datetime.utcnow().isoformat(), macro_id),
        )
