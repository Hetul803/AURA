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
            INSERT OR REPLACE INTO workflow_templates(
                workflow_id, name, command_template, active_version
            ) VALUES (?, ?, ?, ?)
            """,
            ('wf-export', 'Export Workflow', 'Summarize this', 1),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO workflow_versions(
                version_id, workflow_id, version, command_template
            ) VALUES (?, ?, ?, ?)
            """,
            ('wfv-export', 'wf-export', 1, 'Summarize this'),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO workflow_repair_records(
                repair_id, workflow_id, version, failure_reason
            ) VALUES (?, ?, ?, ?)
            """,
            ('wfr-export', 'wf-export', 1, 'target drift'),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO local_profile_account(
                profile_id, display_name, local_user_id
            ) VALUES (?, ?, ?)
            """,
            ('profile-export', 'Local AURA User', 'local-export'),
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
    assert any(row['workflow_id'] == 'wf-export' for row in data['workflow_templates'])
    assert any(row['version_id'] == 'wfv-export' for row in data['workflow_versions'])
    assert any(row['repair_id'] == 'wfr-export' for row in data['workflow_repair_records'])
    assert any(row['profile_id'] == 'profile-export' for row in data['local_profile_account'])
