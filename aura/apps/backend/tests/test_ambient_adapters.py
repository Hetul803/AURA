from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from aura.ambient_adapters import adapter_contracts, classify_ambient_action, create_ambient_routine, list_ambient_routines
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_ambient():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM ambient_routines')


def test_home_and_car_adapter_contracts():
    contracts = {item['surface']: item for item in adapter_contracts()}
    assert 'home' in contracts
    assert 'car' in contracts
    assert 'unlock_door' in contracts['home']['requires_approval']
    assert 'long_form_visual_task_while_driving' in contracts['car']['blocked']


def test_ambient_action_safety_classification():
    home = classify_ambient_action(surface='home', action='unlock the front door')
    assert home['decision'] == 'require_approval'
    assert home['safety_class'] == 'home_security'

    car = classify_ambient_action(surface='car', action='read long report and fill form', driving=True)
    assert car['decision'] == 'defer'
    assert car['safety_class'] == 'driving_limited'

    reminder = classify_ambient_action(surface='home', action='create household routine summary')
    assert reminder['decision'] == 'allow'
    assert reminder['approval_required'] is False


def test_ambient_routine_storage_and_api():
    _clear_ambient()
    routine = create_ambient_routine(
        surface='car',
        name='Defer coding while driving',
        trigger_value='driving_mode',
        action_summary='defer code editing to desktop',
        metadata={'driving': True},
    )
    assert routine['approval_required'] is False
    assert routine['safety_class'] == 'driving_limited'
    assert list_ambient_routines(include_disabled=True)[0]['routine_id'] == routine['routine_id']
    assert list_ambient_routines(surface='car') == []

    contracts = client.get('/ambient/adapters')
    assert contracts.status_code == 200
    assert any(item['surface'] == 'home' for item in contracts.json())

    safety = client.post('/ambient/safety-check', json={'surface': 'car', 'action': 'send a message', 'driving': True})
    assert safety.status_code == 200
    assert safety.json()['decision'] == 'require_approval'

    created = client.post('/ambient/routines', json={
        'surface': 'home',
        'name': 'Morning household reminder',
        'trigger_value': 'weekday_morning',
        'action_summary': 'create household reminder summary',
        'enabled': True,
    })
    assert created.status_code == 200
    assert created.json()['approval_required'] is False
    assert client.get('/ambient/routines', params={'surface': 'home'}).json()[0]['name'] == 'Morning household reminder'


def test_home_car_doc_exists():
    doc = Path('aura/docs/HOME_CAR_ADAPTERS.md')
    assert doc.exists()
    text = doc.read_text(encoding='utf-8')
    assert 'AURA Home' in text
    assert 'AURA Car' in text
    assert 'safety-first' in text
