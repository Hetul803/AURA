from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health():
    assert client.get('/health').status_code == 200


def test_command_and_events():
    r = client.post('/command', json={'text': 'search aura and give me key points'})
    assert r.status_code == 200
    body = r.json()
    assert body['run_id']
    stream = client.get(f"/events/stream/{body['run_id']}")
    assert stream.status_code == 200


def test_model_select():
    assert client.post('/models/select', params={'model_id': 'simple'}).status_code == 200
    assert client.get('/models/select').json()['model_id'] == 'simple'


def test_run_resume_endpoint_exists():
    r = client.post('/command', json={'text': 'open gmail'})
    run_id = r.json()['run_id']
    resumed = client.post(f'/runs/{run_id}/resume')
    assert resumed.status_code == 200


def test_clear_session_endpoint_exists():
    assert client.delete('/browser/session/mail_google_com').status_code == 200


def test_sessions_and_storage_endpoints():
    assert client.get('/browser/sessions').status_code == 200
    assert client.get('/storage/stats').status_code == 200
    assert client.get('/safety/events').status_code == 200
