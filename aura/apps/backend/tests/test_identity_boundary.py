from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from aura.identity_boundary import (
    check_boundary,
    create_identity,
    ensure_default_identities,
    list_boundary_policies,
    list_identities,
    upsert_boundary_policy,
)
from aura.state import db_conn
from storage.db import init_db

client = TestClient(app)


def _clear_identity_tables():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM aura_identities')
        conn.execute('DELETE FROM boundary_policies')


def test_default_identities_and_boundary_policies():
    _clear_identity_tables()
    ensure_default_identities()

    identities = {item['identity_id']: item for item in list_identities()}
    assert identities['personal']['memory_scope'] == 'personal'
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


def test_enterprise_architecture_doc_exists():
    doc = Path('aura/docs/ENTERPRISE_TEAM_ARCHITECTURE.md')
    assert doc.exists()
    text = doc.read_text(encoding='utf-8')
    assert 'RBAC' in text
    assert 'Company AURA' in text
    assert 'Personal AURA' in text
