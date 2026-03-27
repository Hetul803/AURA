from pathlib import Path
from tempfile import TemporaryDirectory

from aura.learning import consolidate_learning, list_preference_memory, list_safety_memory, list_workflow_memory, list_reflection_records, query_relevant_memory
from aura.orchestrator import run_command
from aura.safety import guard_step
from aura.state import db_conn
from aura.steps import Step
from storage.db import init_db


def _clear_learning_tables():
    init_db()
    with db_conn() as conn:
        for table in [
            'reflection_records',
            'workflow_memory',
            'preference_memory',
            'site_memory',
            'safety_memory',
            'memories',
            'preferences',
            'macros',
        ]:
            conn.execute(f'DELETE FROM {table}')


def test_python_run_writes_structured_reflection_and_promotes_success():
    _clear_learning_tables()
    with TemporaryDirectory() as td:
        script = Path(td) / 'buggy.py'
        script.write_text("pritn('hello from aura')\n", encoding='utf-8')

        result = run_command(f'fix and run python script at "{script}"')

        assert result['ok']
        reflection = list_reflection_records(limit=1)[0]
        assert reflection['task_type'] == 'code:python_script'
        assert reflection['outcome'] == 'success'
        assert reflection['repairs_attempted'] >= 1
        assert 'name_error' in reflection['failure_classes_seen']
        assert reflection['repairs_that_worked'][0]['strategy'] == 'repair_python_name'

        workflow = query_relevant_memory(task_type='code:python_script', failure_class='name_error')
        assert workflow['workflow']
        assert workflow['workflow'][0]['strategy'] == 'repair_python_name'


def test_repeated_failed_repair_gets_avoided_on_later_run():
    _clear_learning_tables()

    def run_bad_syntax() -> dict:
        with TemporaryDirectory() as td:
            script = Path(td) / 'bad.py'
            script.write_text("if True print('hello')\n", encoding='utf-8')
            return run_command(f'fix and run python script at "{script}"')

    first = run_bad_syntax()
    second = run_bad_syntax()
    third = run_bad_syntax()

    assert not first['ok']
    assert not second['ok']
    assert not third['ok']
    assert third['run_state']['repair_history'] == []

    workflow_rows = [row for row in list_workflow_memory() if row['pattern_key'] == 'failure_class:syntax_error']
    assert workflow_rows
    assert any(row['failure_count'] >= 2 for row in workflow_rows)


def test_repeated_choices_and_confirmations_promote_preference_and_safety_memory():
    _clear_learning_tables()

    gmail_choices = {'gmail.browser': 'Default', 'gmail.mode': 'Web', 'gmail.account': 'Primary'}
    run_command('open gmail', choices=gmail_choices)
    run_command('open gmail', choices=gmail_choices, use_macro=True)
    run_command('Open Cursor and paste this website prompt: build a modern website')
    run_command('Open Cursor and paste this website prompt: build a modern website')
    consolidate_learning()

    preference_memory = list_preference_memory()
    assert any(row['memory_key'] == 'gmail.browser' and row['value'] == 'Default' for row in preference_memory)

    safety_memory = list_safety_memory()
    assert any(row['action_key'] == 'OS_PASTE' and row['policy'] == 'require_confirmation' for row in safety_memory)

    learned_guard = guard_step(
        Step(id='x', name='Paste text', action_type='OS_PASTE', tool='os', args={'text': 'hi'}),
        task_type='cursor:os',
    )
    assert learned_guard == 'confirm'
