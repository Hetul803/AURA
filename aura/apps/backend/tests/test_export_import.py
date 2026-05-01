import json

from storage.db import get_conn, init_db
from storage.export_import import export_profile


def test_export_profile_includes_learning_tables(tmp_path):
    init_db()
    conn = get_conn()

    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO reflection_records(
                run_id, timestamp, task_type, task_goal, normalized_context, outcome
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ('run-1', '2026-03-18T00:00:00Z', 'browser', 'test export', '{}', 'success'),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO site_memory(
                domain, memory_key, value, last_seen
            ) VALUES (?, ?, ?, ?)
            """,
            ('example.com', 'login_form', 'present', '2026-03-18T00:00:00Z'),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO preference_memory(
                scope, memory_key, value, last_seen
            ) VALUES (?, ?, ?, ?)
            """,
            ('global', 'tone', 'concise', '2026-03-18T00:00:00Z'),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO workflow_memory(
                task_type, pattern_key, strategy, last_seen
            ) VALUES (?, ?, ?, ?)
            """,
            ('browser', 'search-first', 'open docs before acting', '2026-03-18T00:00:00Z'),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO safety_memory(
                scope, action_key, policy, last_seen
            ) VALUES (?, ?, ?, ?)
            """,
            ('global', 'dangerous-write', 'require explicit confirmation', '2026-03-18T00:00:00Z'),
        )

    out = tmp_path / 'profile.json'
    export_profile(str(out))
    data = json.loads(out.read_text(encoding='utf-8'))

    assert any(row['run_id'] == 'run-1' for row in data['reflection_records'])
    assert any(row['domain'] == 'example.com' for row in data['site_memory'])
    assert any(row['memory_key'] == 'tone' for row in data['preference_memory'])
    assert any(row['pattern_key'] == 'search-first' for row in data['workflow_memory'])
    assert any(row['action_key'] == 'dangerous-write' for row in data['safety_memory'])
