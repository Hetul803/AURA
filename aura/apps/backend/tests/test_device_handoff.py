from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from aura.device_handoff import create_handoff, get_handoff, list_handoffs, update_handoff
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_handoffs():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM device_handoffs')


def test_device_handoff_crud():
    _clear_handoffs()
    handoff = create_handoff(
        source_device='desktop-local',
        target_device='phone-companion',
        run_id='run-1',
        approval_required=True,
        payload={'type': 'approval_card', 'action': 'paste_reply'},
    )

    assert handoff['approval_required'] is True
    assert handoff['payload']['action'] == 'paste_reply'
    assert get_handoff(handoff['handoff_id'])['target_device'] == 'phone-companion'
    assert list_handoffs(target_device='phone-companion')[0]['handoff_id'] == handoff['handoff_id']

    updated = update_handoff(handoff['handoff_id'], status='approved', payload={'type': 'approval_card', 'approved': True})
    assert updated['status'] == 'approved'
    assert updated['payload']['approved'] is True


def test_device_handoff_api_contracts():
    _clear_handoffs()
    created = client.post('/devices/handoffs', json={
        'source_device': 'phone-companion',
        'target_device': 'desktop-local',
        'payload': {'command': 'continue coding task'},
        'approval_required': False,
    })
    assert created.status_code == 200
    handoff_id = created.json()['handoff_id']

    listed = client.get('/devices/handoffs', params={'target_device': 'desktop-local'})
    assert listed.status_code == 200
    assert listed.json()[0]['handoff_id'] == handoff_id

    patched = client.patch(f'/devices/handoffs/{handoff_id}', json={'status': 'accepted'})
    assert patched.status_code == 200
    assert patched.json()['status'] == 'accepted'

    assert client.get(f'/devices/handoffs/{handoff_id}').status_code == 200
    assert client.get('/devices/handoffs/missing').status_code == 404


def test_cross_device_architecture_doc_exists():
    doc = Path('aura/docs/CROSS_DEVICE_ARCHITECTURE.md')
    assert doc.exists()
    text = doc.read_text(encoding='utf-8')
    assert 'Phone' in text
    assert 'Enterprise' in text
    assert 'handoff' in text.lower()
