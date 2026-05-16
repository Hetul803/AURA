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
from aura.orchestrator import run_command
from aura.memory_engine import list_memory_items
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


def test_enterprise_architecture_doc_exists():
    doc = Path(__file__).resolve().parents[3] / 'docs/ENTERPRISE_TEAM_ARCHITECTURE.md'
    assert doc.exists()
    text = doc.read_text(encoding='utf-8')
    assert 'RBAC' in text
    assert 'Company AURA' in text
    assert 'Personal AURA' in text
