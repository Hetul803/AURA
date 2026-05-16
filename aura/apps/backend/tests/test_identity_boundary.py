from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from aura.identity_boundary import (
    get_active_identity,
    check_boundary,
    create_identity,
    ensure_default_identities,
    list_boundary_policies,
    list_identities,
    memory_scope_decision,
    set_active_identity,
    upsert_boundary_policy,
)
from aura.crypto_identity import identity_attestation, list_identity_keys, sign_identity_payload, verify_identity_signature
from aura.licensing import generate_dev_license_token
from aura.orchestrator import run_command
from aura.memory_engine import encrypt_existing_memory_items, list_memory_items
from aura.state import list_audit_log
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_identity_tables():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM aura_identities')
        conn.execute('DELETE FROM boundary_policies')
        conn.execute("DELETE FROM profile_meta WHERE key='active_identity_id'")


def test_default_identities_and_boundary_policies():
    _clear_identity_tables()
    ensure_default_identities()

    identities = {item['identity_id']: item for item in list_identities()}
    assert identities['personal']['memory_scope'] == 'personal'
    assert identities['work']['memory_scope'] == 'work'
    assert identities['session']['memory_scope'] == 'session'
    assert identities['company']['policy_scope'] == 'enterprise'

    decision = check_boundary(
        source_identity='company',
        target_identity='personal',
        data_class='company_confidential',
        action='remember',
    )
    assert decision['decision'] == 'deny'

    personal_to_company = check_boundary(
        source_identity='personal',
        target_identity='company',
        data_class='personal_private',
        action='share',
    )
    assert personal_to_company['decision'] == 'require_approval'


def test_active_identity_and_memory_scope_policy():
    _clear_identity_tables()
    ensure_default_identities()

    assert get_active_identity()['identity_id'] == 'personal'
    active = set_active_identity('work')
    assert active['memory_scope'] == 'work'
    assert get_active_identity()['identity_id'] == 'work'

    allowed = memory_scope_decision(requested_scope='work', action='remember')
    assert allowed['decision'] == 'allow'

    cross_scope = memory_scope_decision(requested_scope='personal', action='remember')
    assert cross_scope['decision'] == 'require_approval'
    assert 'Personal memory' in cross_scope['reason']


def test_custom_identity_policy_allows_team_transfer():
    _clear_identity_tables()
    create_identity(name='Team AURA', identity_id='team-eng', identity_type='team', owner='company', memory_scope='company:eng', policy_scope='enterprise')
    upsert_boundary_policy(
        source_identity='team-eng',
        target_identity='company',
        data_class='work_status',
        action='share',
        decision='allow',
        reason='Work status is shareable inside company boundary.',
    )

    decision = check_boundary(source_identity='team-eng', target_identity='company', data_class='work_status', action='share')
    assert decision['decision'] == 'allow'
    assert 'company boundary' in decision['reason']


def test_identity_boundary_api_contracts():
    _clear_identity_tables()
    listed = client.get('/identities')
    assert listed.status_code == 200
    assert any(item['identity_id'] == 'personal' for item in listed.json())

    active = client.get('/identities/active')
    assert active.status_code == 200
    assert active.json()['identity_id'] == 'personal'

    switched = client.post('/identities/active', json={'identity_id': 'work'})
    assert switched.status_code == 200
    assert switched.json()['identity_id'] == 'work'

    created = client.post('/identities', json={
        'identity_id': 'department-sales',
        'name': 'Sales AURA',
        'identity_type': 'department',
        'owner': 'company',
        'memory_scope': 'company:sales',
        'policy_scope': 'enterprise',
    })
    assert created.status_code == 200

    policy = client.post('/boundaries/policies', json={
        'source_identity': 'department-sales',
        'target_identity': 'company',
        'data_class': 'pipeline_summary',
        'action': 'share',
        'decision': 'allow',
        'reason': 'Department summaries can be shared with company AURA.',
    })
    assert policy.status_code == 200

    checked = client.post('/boundaries/check', json={
        'source_identity': 'department-sales',
        'target_identity': 'company',
        'data_class': 'pipeline_summary',
        'action': 'share',
    })
    assert checked.status_code == 200
    assert checked.json()['decision'] == 'allow'
    assert client.get('/boundaries/policies').status_code == 200


def test_memory_api_respects_active_identity_scope():
    _clear_identity_tables()
    with db_conn() as conn:
        conn.execute('DELETE FROM memory_items')
    client.post('/identities/active', json={'identity_id': 'work'})

    blocked = client.post('/memory/items', json={
        'kind': 'preference',
        'key': 'personal.note',
        'value': 'Use personal voice for weekend writing.',
        'scope': 'personal',
    })
    assert blocked.status_code == 200
    assert blocked.json()['rejected'] is True
    assert 'identity_boundary' in blocked.json()['reasons'][0]

    created = client.post('/memory/items', json={
        'kind': 'preference',
        'key': 'work.tone',
        'value': 'Use concise executive summaries for work updates.',
        'scope': 'work',
    })
    assert created.status_code == 200
    assert created.json()['stored'] is True

    searched = client.post('/memory/search', json={'query': 'executive summaries'})
    assert searched.status_code == 200
    assert searched.json()[0]['scope'] == 'work'


def test_command_memory_and_audit_use_active_identity():
    _clear_identity_tables()
    with db_conn() as conn:
        conn.execute('DELETE FROM memory_items')
        conn.execute('DELETE FROM audit_log')
    set_active_identity('work')

    result = run_command(
        'remember I prefer concise executive summaries',
        context={'ok': True, 'active_app': 'Fixture', 'workspace_hint': '/tmp/aura-test'},
    )

    assert result['ok'] is True
    items = list_memory_items(scope='work')
    assert items
    assert items[0]['metadata']['active_identity'] == 'work'
    audit = list_audit_log(limit=20)
    assert any((row.get('payload') or {}).get('identity_id') == 'work' for row in audit)
    assert any((row.get('payload') or {}).get('identity_signature') for row in audit)


def test_identity_attestation_creates_ed25519_key():
    _clear_identity_tables()
    ensure_default_identities()

    attestation = identity_attestation(get_active_identity())

    assert attestation['key']['algorithm'] == 'ed25519'
    assert attestation['key']['fingerprint']
    assert attestation['copy_resistance']['private_key_encrypted_at_rest'] is True
    assert list_identity_keys('personal')

    signature = sign_identity_payload('personal', {'action': 'demo', 'scope': 'personal'})
    assert signature['signature']
    public_key = attestation['key']['public_key_pem']
    assert verify_identity_signature(public_key, {'action': 'demo', 'scope': 'personal'}, signature['signature'])


def test_memory_values_are_encrypted_at_rest_but_decrypted_for_use():
    _clear_identity_tables()
    with db_conn() as conn:
        conn.execute('DELETE FROM memory_items')
    ensure_default_identities()

    result = client.post('/memory/items', json={
        'kind': 'preference',
        'key': 'writing.style',
        'value': 'I prefer concise technical explanations.',
        'scope': 'personal',
    })

    assert result.status_code == 200
    body = result.json()
    assert body['stored'] is True
    assert body['value'] == 'I prefer concise technical explanations.'
    assert body['encrypted_at_rest'] is True
    row = db_conn().execute('SELECT value FROM memory_items WHERE memory_id=?', (body['memory_id'],)).fetchone()
    assert row['value'].startswith('enc:v1:')
    assert 'concise technical' not in row['value']


def test_existing_plaintext_memory_items_are_migrated_to_encrypted_storage():
    _clear_identity_tables()
    with db_conn() as conn:
        conn.execute('DELETE FROM memory_items')
        conn.execute(
            '''
            INSERT INTO memory_items(memory_id, scope, kind, memory_key, value, tags_json, confidence, source, permission)
            VALUES('mem_plaintext_fixture','personal','preference','workspace.path','Use /Users/me/AURA workspaces','[]',0.8,'fixture','private')
            '''
        )

    migrated = encrypt_existing_memory_items()

    assert migrated['encrypted'] == 1
    row = db_conn().execute("SELECT value FROM memory_items WHERE memory_id='mem_plaintext_fixture'").fetchone()
    assert row['value'].startswith('enc:v1:')
    assert 'AURA workspaces' not in row['value']
    item = list_memory_items(scope='personal')[0]
    assert item['value'] == 'Use /Users/me/AURA workspaces'


def test_signed_license_token_requires_configured_vendor_key(monkeypatch):
    monkeypatch.delenv('AURA_LICENSE_PUBLIC_KEY', raising=False)
    token = 'payload.signature'
    response = client.post('/license/activate', json={'token': token})
    assert response.status_code == 400
    assert response.json()['detail']['status'] == 'license_server_not_configured'


def test_signed_license_token_activates_with_vendor_public_key(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private = ed25519.Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('utf-8')
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('utf-8')
    monkeypatch.setenv('AURA_LICENSE_PUBLIC_KEY', public_pem)
    with db_conn() as conn:
        conn.execute('DELETE FROM license_records')

    token = generate_dev_license_token(private_pem, {
        'license_id': 'lic_test',
        'account_email': 'alpha@example.com',
        'tier': 'private_alpha',
        'features': {'guardian': True, 'encrypted_memory': True},
    })
    response = client.post('/license/activate', json={'token': token})

    assert response.status_code == 200
    body = response.json()
    assert body['activated'] is True
    assert body['tier'] == 'private_alpha'
    assert body['signature_status'] == 'ed25519_verified'


def test_enterprise_architecture_doc_exists():
    doc = Path(__file__).resolve().parents[3] / 'docs/ENTERPRISE_TEAM_ARCHITECTURE.md'
    assert doc.exists()
    text = doc.read_text(encoding='utf-8')
    assert 'RBAC' in text
    assert 'Company AURA' in text
    assert 'Personal AURA' in text
