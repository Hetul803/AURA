from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from aura.mobile_companion import (
    create_mobile_approval_card,
    create_pairing_code,
    decide_mobile_handoff,
    list_mobile_devices,
    mobile_inbox,
    register_mobile_device,
)
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_mobile():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM mobile_devices')
        conn.execute('DELETE FROM device_handoffs')


def test_mobile_pairing_device_and_inbox():
    _clear_mobile()
    pairing = create_pairing_code()
    assert len(pairing['pairing_code']) == 6

    device = register_mobile_device(device_name='Hetul Phone', pairing_code=pairing['pairing_code'], capabilities=['approval_inbox'])
    assert device['device_name'] == 'Hetul Phone'
    assert list_mobile_devices()[0]['device_id'] == device['device_id']

    card = create_mobile_approval_card(run_id='run-1', title='Approve paste', body='Paste reply into Gmail?', action='paste_reply')
    inbox = mobile_inbox(device['device_id'])
    assert inbox[0]['handoff_id'] == card['handoff_id']
    assert inbox[0]['payload']['type'] == 'approval_card'

    decided = decide_mobile_handoff(card['handoff_id'], 'approve')
    assert decided['status'] == 'approved'


def test_mobile_api_contracts():
    _clear_mobile()
    pairing = client.post('/mobile/pairing-code')
    assert pairing.status_code == 200

    device = client.post('/mobile/devices', json={
        'device_name': 'Private Alpha Phone',
        'pairing_code': pairing.json()['pairing_code'],
        'capabilities': ['approval_inbox', 'run_status'],
    })
    assert device.status_code == 200
    device_id = device.json()['device_id']

    card = client.post('/mobile/approval-cards', json={
        'run_id': 'run-2',
        'title': 'Approve action',
        'body': 'Allow AURA to continue?',
        'action': 'continue_run',
    })
    assert card.status_code == 200
    handoff_id = card.json()['handoff_id']

    assert client.get('/mobile/status', params={'device_id': device_id}).json()['pending_handoffs'] == 1
    assert client.get('/mobile/inbox', params={'device_id': device_id}).json()[0]['handoff_id'] == handoff_id
    decided = client.post(f'/mobile/handoffs/{handoff_id}/decision', json={'decision': 'reject'})
    assert decided.status_code == 200
    assert decided.json()['status'] == 'rejected'
    assert client.get('/mobile/devices').json()[0]['device_id'] == device_id


def test_mobile_companion_doc_exists():
    doc = Path(__file__).resolve().parents[3] / 'docs/MOBILE_COMPANION_PROTOTYPE.md'
    assert doc.exists()
    text = doc.read_text(encoding='utf-8')
    assert 'approval' in text.lower()
    assert '/mobile/inbox' in text
