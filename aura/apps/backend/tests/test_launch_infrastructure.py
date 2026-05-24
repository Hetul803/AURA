from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_launch_status_reports_license_update_and_crash_service_configuration(monkeypatch):
    monkeypatch.setenv('AURA_LICENSE_SERVER_URL', 'https://alpha.example.com')
    monkeypatch.delenv('AURA_UPDATE_FEED_URL', raising=False)
    response = client.get('/launch/status')
    body = response.json()

    assert response.status_code == 200
    assert body['launch_services']['license_server_configured'] is True
    assert body['launch_services']['update_feed_configured'] is True
    assert body['launch_services']['crash_reporting_configured'] is True


def test_update_check_is_honest_when_feed_missing(monkeypatch):
    monkeypatch.delenv('AURA_LICENSE_SERVER_URL', raising=False)
    monkeypatch.delenv('AURA_UPDATE_FEED_URL', raising=False)
    response = client.get('/updates/latest', params={'current_version': '1.0.0'})
    body = response.json()

    assert response.status_code == 200
    assert body['ok'] is False
    assert body['status'] == 'update_feed_not_configured'
    assert 'Manual DMG updates still work' in body['message']


def test_crash_report_redacts_secrets_and_stays_local_without_server(monkeypatch):
    monkeypatch.delenv('AURA_LICENSE_SERVER_URL', raising=False)
    monkeypatch.delenv('AURA_CRASH_REPORT_URL', raising=False)
    response = client.post('/crash/report', json={
        'source': 'test',
        'message': 'renderer error',
        'stack': 'password=test123 sk_test_should_not_leave_machine',
        'metadata': {'api_key': 'abc123'},
    })
    body = response.json()
    encoded = str(body)

    assert response.status_code == 200
    assert body['ok'] is False
    assert body['status'] == 'crash_reporting_not_configured'
    assert 'test123' not in encoded
    assert 'sk_test_should_not_leave_machine' not in encoded
    assert 'abc123' not in encoded


def test_launch_env_template_documents_replaceable_keys():
    response = client.get('/launch/env-template')
    body = response.json()

    assert response.status_code == 200
    assert body['ok'] is True
    assert 'STRIPE_SECRET_KEY' in body['env']
    assert 'AURA_LICENSE_SERVER_URL' in body['env']
