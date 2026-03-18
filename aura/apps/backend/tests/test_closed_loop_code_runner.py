from pathlib import Path
from tempfile import TemporaryDirectory

from aura.orchestrator import run_command
from aura.memory import latest_memory
from aura.state import db_conn



def test_flagship_code_workflow_repairs_and_reruns_python_script():
    with db_conn() as conn:
        conn.execute('DELETE FROM macros')
    with TemporaryDirectory() as td:
        script = Path(td) / 'buggy.py'
        script.write_text("pritn('hello from aura')\n", encoding='utf-8')

        result = run_command(f'fix and run python script at "{script}"')

        assert result['ok']
        run_step = next(step for step in result['steps'] if step['step'] == 's2')
        assert run_step['status'] == 'success'
        assert "print('hello from aura')" in script.read_text(encoding='utf-8')
        assert latest_memory(f'exec:script:{script}:repair') is not None
