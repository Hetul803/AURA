from pathlib import Path
from tempfile import TemporaryDirectory

from aura.orchestrator import run_command
from aura.memory import latest_memory
from aura.state import db_conn



def _clear_macros():
    with db_conn() as conn:
        conn.execute('DELETE FROM macros')



def test_name_error_workflow_repairs_and_reruns_python_script():
    _clear_macros()
    with TemporaryDirectory() as td:
        script = Path(td) / 'buggy.py'
        script.write_text("pritn('hello from aura')\n", encoding='utf-8')

        result = run_command(f'fix and run python script at "{script}"')

        assert result['ok']
        run_step = next(step for step in result['steps'] if step['step'] == 's2')
        assert run_step['status'] == 'success'
        assert "print('hello from aura')" in script.read_text(encoding='utf-8')
        assert latest_memory(f'exec:script:{script}:name_error:repair_success') is not None



def test_syntax_error_workflow_repairs_and_reruns_python_script():
    _clear_macros()
    with TemporaryDirectory() as td:
        script = Path(td) / 'buggy.py'
        script.write_text("def greet()\n    print('hello')\n\ngreet()\n", encoding='utf-8')

        result = run_command(f'fix and run python script at "{script}"')

        assert result['ok']
        assert 'def greet():' in script.read_text(encoding='utf-8')
        assert latest_memory(f'exec:script:{script}:syntax_error:repair_success') is not None



def test_unrecoverable_runtime_error_stops_with_terminal_failure_and_memory():
    _clear_macros()
    with TemporaryDirectory() as td:
        script = Path(td) / 'buggy.py'
        script.write_text("print(1/0)\n", encoding='utf-8')

        result = run_command(f'fix and run python script at "{script}"')

        assert not result['ok']
        run_state = result['run_state']
        assert run_state['terminal_outcome'] == 'failed'
        assert run_state['last_failure_class'] == 'runtime_error'
        assert latest_memory('exec:code:python_script:failure') is not None
