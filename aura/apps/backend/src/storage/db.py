from __future__ import annotations
import sqlite3
from .profile_paths import profile_dir

SCHEMA = [
"""CREATE TABLE IF NOT EXISTS memories(
  id INTEGER PRIMARY KEY,
  key TEXT,
  value TEXT,
  tags TEXT DEFAULT '',
  importance INTEGER DEFAULT 0,
  pinned INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);""",
"""CREATE TABLE IF NOT EXISTS preferences(
  id INTEGER PRIMARY KEY,
  decision_key TEXT UNIQUE,
  value TEXT,
  confidence REAL DEFAULT 0.5,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);""",
"""CREATE TABLE IF NOT EXISTS macros(
  id TEXT PRIMARY KEY,
  name TEXT,
  trigger_signature TEXT,
  steps_template TEXT,
  enabled INTEGER DEFAULT 1,
  success_count INTEGER DEFAULT 0,
  last_used TEXT
);""",
"""CREATE TABLE IF NOT EXISTS actions_log(
  id INTEGER PRIMARY KEY,
  run_id TEXT,
  step_id TEXT,
  status TEXT,
  detail TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);""",
"""CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, kind TEXT, payload TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);""",
"""CREATE TABLE IF NOT EXISTS profile_meta(key TEXT PRIMARY KEY, value TEXT);""",
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(profile_dir() / "aura.sqlite3"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    with conn:
        for stmt in SCHEMA:
            conn.execute(stmt)
        # Backward-compat migrations for older local dbs
        for col, ddl in {
            "tags": "ALTER TABLE memories ADD COLUMN tags TEXT DEFAULT ''",
            "pinned": "ALTER TABLE memories ADD COLUMN pinned INTEGER DEFAULT 0",
        }.items():
            cols = [r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()]
            if col not in cols:
                conn.execute(ddl)
