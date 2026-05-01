from fastapi.testclient import TestClient

from api.main import app
from aura.memory import write_memory
from aura.memory_engine import (
    compact_memory_items,
    delete_memory_item,
    list_memory_items,
    memory_lifecycle_sweep,
    remember_item,
    reinforce_memory_item,
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


def test_duplicate_memory_merge_and_reinforcement():
    _clear_memory_items()
    first = remember_item(kind='preference', key='writing.tone', value='Use direct wording.', confidence=0.55, source='auto')
    second = remember_item(kind='preference', key='writing.tone', value='Use direct wording.', confidence=0.55, source='auto')

    assert second['merged'] is True
    reinforced = reinforce_memory_item(first['memory_id'], evidence='approved_draft')
    assert reinforced['usage_count'] >= 2
    assert reinforced['confidence'] > first['confidence']


def test_memory_quality_rejects_junk_and_sensitive_public_memory():
    _clear_memory_items()
    junk = remember_item(kind='fact', key='last_result', value='ok', confidence=0.5, source='auto')
    sensitive = remember_item(kind='fact', key='api_key', value='api_key secret token value', permission='shared', confidence=0.9)

    assert junk['rejected'] is True
    assert 'low_information_value' in junk['reasons']
    assert sensitive['rejected'] is True
    assert 'sensitive_requires_private_permission' in sensitive['reasons']
    assert list_memory_items() == []


def test_memory_compaction_archives_raw_records_and_creates_summary():
    _clear_memory_items()
    for i in range(3):
        item = remember_item(kind='workflow', key=f'gmail.reply.{i}', value=f'Reply workflow pattern {i}', tags=['assist:writing'], confidence=0.6)
        update_memory_item(item['memory_id'], updated_at='2025-01-01T00:00:00+00:00')

    compacted = compact_memory_items(kind='workflow', older_than_days=1)

    assert compacted['summaries_created'] == 1
    summaries = list_memory_items(kind='summary')
    assert summaries
    assert summaries[0]['metadata']['raw_count'] == 3
    assert len(list_memory_items(kind='workflow')) == 0


def test_memory_retrieval_ranking_uses_scope_task_usage_and_recency():
    _clear_memory_items()
    weak = remember_item(kind='project', key='repo', value='Old unrelated repo note', scope='work', confidence=0.9)
    strong = remember_item(kind='project', key='repo', value='AURA github clone workflow repo note', scope='personal', confidence=0.6, tags=['github:clone'], metadata={'task_type': 'github:clone'})
    reinforce_memory_item(strong['memory_id'], evidence='used_in_clone', confidence_delta=0.05)

    ranked = search_memory_items('github clone repo', scope='personal', task_type='github:clone', limit=2)

    assert ranked[0]['memory_id'] == strong['memory_id']
    assert all(item['memory_id'] != weak['memory_id'] for item in ranked)


def test_memory_lifecycle_sweep_decays_and_archives_stale_low_value_items():
    _clear_memory_items()
    low = remember_item(kind='context', key='old.context', value='Old context memory', confidence=0.2)
    high = remember_item(kind='fact', key='old.fact', value='Important old project fact', confidence=0.8)
    update_memory_item(low['memory_id'], confidence=0.2, updated_at='2024-01-01T00:00:00+00:00')
    update_memory_item(high['memory_id'], updated_at='2024-01-01T00:00:00+00:00')

    result = memory_lifecycle_sweep(stale_after_days=30, low_confidence=0.25)

    assert low['memory_id'] in result['archived']
    assert high['memory_id'] in result['decayed']


def test_memory_compaction_api_contract():
    _clear_memory_items()
    for i in range(2):
        item = remember_item(kind='failure', key=f'paste.failure.{i}', value=f'Paste target failed {i}', confidence=0.5)
        update_memory_item(item['memory_id'], updated_at='2025-01-01T00:00:00+00:00')

    compacted = client.post('/memory/compact', json={'kind': 'failure', 'older_than_days': 1})

    assert compacted.status_code == 200
    assert compacted.json()['summaries_created'] == 1
