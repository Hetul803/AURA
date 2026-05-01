from fastapi.testclient import TestClient

from api.main import app
from aura.memory import write_memory
from aura.memory_engine import (
    delete_memory_item,
    list_memory_items,
    remember_item,
    search_memory_items,
    update_memory_item,
)
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_memory_items():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM memory_items')
        conn.execute('DELETE FROM memories')


def test_memory_item_crud_search_and_archive():
    _clear_memory_items()
    item = remember_item(
        kind='preference',
        key='writing.tone',
        value='Use direct, warm, concise wording.',
        tags=['writing', 'style'],
        confidence=0.85,
        pinned=True,
        metadata={'source_run': 'manual-test'},
    )

    assert item['scope'] == 'personal'
    assert item['permission'] == 'private'
    assert item['pinned'] is True
    assert item['tags'] == ['writing', 'style']

    found = list_memory_items(q='tone')
    assert found[0]['memory_id'] == item['memory_id']

    ranked = search_memory_items('warm writing')
    assert ranked[0]['memory_id'] == item['memory_id']
    assert ranked[0]['score'] > 0

    updated = update_memory_item(item['memory_id'], value='Use crisp founder-style writing.', archived=False)
    assert updated['value'] == 'Use crisp founder-style writing.'

    archived = update_memory_item(item['memory_id'], archived=True)
    assert archived['archived'] is True
    assert all(row['memory_id'] != item['memory_id'] for row in list_memory_items())
    assert any(row['memory_id'] == item['memory_id'] for row in list_memory_items(include_archived=True))

    assert delete_memory_item(item['memory_id']) is True


def test_legacy_memory_write_mirrors_to_typed_memory_items():
    _clear_memory_items()
    write_memory('project.folder', 'C:/Users/example/Projects', ['preference', 'filesystem'], importance=4, pinned=1)

    items = list_memory_items(q='project.folder')
    assert items
    assert items[0]['memory_key'] == 'project.folder'
    assert items[0]['kind'] == 'preference'
    assert items[0]['source'] == 'legacy_memory'
    assert items[0]['pinned'] is True


def test_memory_api_contracts():
    _clear_memory_items()
    created = client.post('/memory/items', json={
        'kind': 'workflow',
        'key': 'github.clone.folder',
        'value': 'Clone repositories into Documents/New project by default.',
        'tags': ['github', 'workspace'],
        'confidence': 0.75,
    })
    assert created.status_code == 200
    memory_id = created.json()['memory_id']

    listed = client.get('/memory/items', params={'q': 'clone'})
    assert listed.status_code == 200
    assert listed.json()[0]['memory_id'] == memory_id

    searched = client.post('/memory/search', json={'query': 'where should github repos go', 'limit': 5})
    assert searched.status_code == 200
    assert any(item['memory_id'] == memory_id for item in searched.json())

    patched = client.patch(f'/memory/items/{memory_id}', json={'pinned': True, 'permission': 'private'})
    assert patched.status_code == 200
    assert patched.json()['pinned'] is True

    deleted = client.delete(f'/memory/items/{memory_id}')
    assert deleted.status_code == 200
    assert deleted.json()['archived'] is True

    missing = client.patch('/memory/items/missing', json={'value': 'nope'})
    assert missing.status_code == 404
