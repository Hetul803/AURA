from aura.orchestrator import run_command
from aura.state import db_conn


def test_macro_record_and_replay_suggestion():
    with db_conn() as conn:
        conn.execute('DELETE FROM macros')
    first = run_command('search cats and give me key points')
    assert first['ok']
    second = run_command('search dogs and give me key points')
    assert second.get('macro_suggestion') is not None
    third = run_command('search dogs and give me key points', use_macro=True)
    assert third['ok']
