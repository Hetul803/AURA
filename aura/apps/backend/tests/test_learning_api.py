from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from api.main import app
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


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


def test_learning_api_exposes_reflections_memory_query_and_consolidation():
    _clear_learning_tables()
    with TemporaryDirectory() as td:
        script = Path(td) / 'buggy.py'
        script.write_text("pritn('hello')\n", encoding='utf-8')
        run = client.post('/command', json={'text': f'fix and run python script at "{script}"'})
        assert run.status_code == 200
        assert run.json()['ok']

    reflections = client.get('/learning/reflections')
    assert reflections.status_code == 200
    assert reflections.json()

    workflow = client.get('/learning/memory/workflow')
    assert workflow.status_code == 200
    assert workflow.json()

    query = client.post('/learning/query', json={'task_type': 'code:python_script', 'failure_class': 'name_error', 'limit': 3})
    assert query.status_code == 200
    assert query.json()['workflow']

    consolidation = client.post('/learning/consolidate')
    assert consolidation.status_code == 200
    assert 'workflow_entries' in consolidation.json()
