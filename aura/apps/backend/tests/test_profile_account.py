from fastapi.testclient import TestClient

from api.main import app
from aura.profile_account import ensure_local_profile, update_profile_status
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_profile():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM local_profile_account')


def test_local_profile_defaults_are_local_first_and_subscription_ready():
    _clear_profile()
    profile = ensure_local_profile()

    assert profile['subscription_tier'] == 'local_free'
    assert profile['billing_status'] == 'local_only'
    assert profile['cloud_sync_enabled'] is False
    assert profile['usage_limits']['memory_items'] > 0
    assert profile['cloud_storage_target']['provider'] == 'none'


def test_profile_status_update_preserves_local_first_mode():
    _clear_profile()
    updated = update_profile_status(
        subscription_tier='trial',
        trial_state='active',
        usage_limits={'monthly_agent_runs': 25, 'memory_items': 1000},
        cloud_storage_target={'provider': 'google_drive', 'encrypted_backup_enabled': False},
    )

    assert updated['subscription_tier'] == 'trial'
    assert updated['trial_state'] == 'active'
    assert updated['cloud_sync_enabled'] is False
    assert updated['cloud_storage_target']['provider'] == 'google_drive'


def test_profile_status_api_contract():
    _clear_profile()
    status = client.get('/profile/status')
    assert status.status_code == 200
    assert status.json()['billing_status'] == 'local_only'

    patched = client.patch('/profile/status', json={'device_limit': 3, 'subscription_tier': 'paid_monthly'})
    assert patched.status_code == 200
    assert patched.json()['device_limit'] == 3
    assert patched.json()['subscription_tier'] == 'paid_monthly'
