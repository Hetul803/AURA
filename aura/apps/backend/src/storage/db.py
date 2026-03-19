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
"""CREATE TABLE IF NOT EXISTS reflection_records(
  run_id TEXT PRIMARY KEY,
  timestamp TEXT,
  task_type TEXT,
  task_goal TEXT,
  normalized_context TEXT,
  outcome TEXT,
  failure_classes_seen TEXT,
  repairs_attempted INTEGER DEFAULT 0,
  repairs_that_worked TEXT,
  repairs_that_failed TEXT,
  user_intervention_required INTEGER DEFAULT 0,
  tool_sequence_used TEXT,
  useful_observations TEXT,
  candidate_preferences TEXT,
  candidate_workflow_patterns TEXT,
  candidate_site_memory TEXT,
  candidate_safety_memory TEXT,
  future_hints TEXT,
  confidence_signals TEXT,
  confidence REAL DEFAULT 0.0
);""",
"""CREATE TABLE IF NOT EXISTS site_memory(
  id INTEGER PRIMARY KEY,
  domain TEXT,
  memory_key TEXT,
  value TEXT,
  confidence REAL DEFAULT 0.5,
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,
  last_seen TEXT,
  UNIQUE(domain, memory_key, value)
);""",
"""CREATE TABLE IF NOT EXISTS preference_memory(
  id INTEGER PRIMARY KEY,
  scope TEXT,
  memory_key TEXT,
  value TEXT,
  confidence REAL DEFAULT 0.5,
  evidence_count INTEGER DEFAULT 0,
  last_seen TEXT,
  UNIQUE(scope, memory_key, value)
);""",
"""CREATE TABLE IF NOT EXISTS workflow_memory(
  id INTEGER PRIMARY KEY,
  task_type TEXT,
  pattern_key TEXT,
  strategy TEXT,
  confidence REAL DEFAULT 0.5,
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,
  last_seen TEXT,
  notes TEXT,
  UNIQUE(task_type, pattern_key, strategy)
);""",
"""CREATE TABLE IF NOT EXISTS safety_memory(
  id INTEGER PRIMARY KEY,
  scope TEXT,
  action_key TEXT,
  policy TEXT,
  confidence REAL DEFAULT 0.5,
  evidence_count INTEGER DEFAULT 0,
  last_seen TEXT,
  UNIQUE(scope, action_key, policy)
);""",
]



def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(profile_dir() / 'aura.sqlite3'), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn



def init_db() -> None:
    conn = get_conn()
    with conn:
        for stmt in SCHEMA:
            conn.execute(stmt)
        for col, ddl in {
            'tags': "ALTER TABLE memories ADD COLUMN tags TEXT DEFAULT ''",
            'pinned': 'ALTER TABLE memories ADD COLUMN pinned INTEGER DEFAULT 0',
        }.items():
            cols = [r[1] for r in conn.execute('PRAGMA table_info(memories)').fetchall()]
            if col not in cols:
                conn.execute(ddl)
        reflection_cols = [r[1] for r in conn.execute('PRAGMA table_info(reflection_records)').fetchall()]
        if 'confidence_signals' not in reflection_cols:
            conn.execute("ALTER TABLE reflection_records ADD COLUMN confidence_signals TEXT DEFAULT ''")
