import json

from fastapi.testclient import TestClient

from api.main import app
from aura.guardian_policy import guardian_policy, update_guardian_policy
from aura.memory_engine import memory_health, remember_item
from aura.planner import plan_from_text
from aura.safety import step_risk
from aura.state import GUARDIAN_EVENTS, db_conn, list_guardian_events
from aura.steps import Step
from storage.db import init_db


client = TestClient(app)


def _reset_product_state():
    init_db()
    with db_conn() as conn:
        for table in ['memory_items', 'audit_log']:
            conn.execute(f'DELETE FROM {table}')
        conn.execute("DELETE FROM profile_meta WHERE key IN ('guardian_policy','external_agent_mediation')")
    GUARDIAN_EVENTS.clear()


def test_guardian_policy_modes_and_trust_rules_affect_safety():
    _reset_product_state()
    update_guardian_policy({'mode': 'strict'})
    step = Step(id='ls', name='List files', action_type='CODE_RUN', tool='code', args={'kind': 'shell', 'command': 'ls', 'workspace': '/tmp'})
    assert step_risk(step)['decision'] == 'confirm'

    update_guardian_policy({'mode': 'balanced', 'trusted_command_patterns': ['^npm run test$']})
    safe = Step(id='test', name='Run tests', action_type='CODE_RUN', tool='code', args={'kind': 'shell', 'command': 'npm run test', 'workspace': '/tmp'})
    assert step_risk(safe)['decision'] == 'allow'

    update_guardian_policy({'blocked_command_patterns': ['deploy-prod']})
    blocked = Step(id='deploy', name='Deploy', action_type='CODE_RUN', tool='code', args={'kind': 'shell', 'command': 'deploy-prod --force', 'workspace': '/tmp'})
    decision = step_risk(blocked)
    assert decision['decision'] == 'blocked'
    assert decision['reason'] == 'guardian_blocked_command_pattern'


def test_guardian_policy_api_and_coverage():
    _reset_product_state()
    patched = client.patch('/guardian/policy', json={'mode': 'strict', 'trusted_domains': ['github.com']})
    assert patched.status_code == 200
    assert patched.json()['mode'] == 'strict'
    assert 'github.com' in client.get('/guardian/policy').json()['trusted_domains']
    coverage = client.get('/guardian/coverage').json()
    assert 'AURA commands' in coverage['protected_today']
    assert 'true OS-wide monitoring' in coverage['planned']


def test_guardian_ledger_filters_persistent_audit_events():
    _reset_product_state()
    response = client.post('/memory/items', json={'kind': 'fact', 'key': 'service.password', 'value': 'password=test12345', 'permission': 'private'})
    assert response.json()['rejected'] is True
    ledger = client.get('/guardian/ledger', params={'category': 'memory_rejected'}).json()
    assert ledger
    assert ledger[0]['category'] == 'memory_rejected'
    assert ledger[0]['approval_status'] == 'blocked'


def test_memory_health_and_import_preview(tmp_path):
    _reset_product_state()
    remember_item(kind='preference', key='writing.tone', value='Use concise technical language.', pinned=True)
    health = memory_health()
    assert health['active_memories'] == 1
    assert health['pinned_memories'] == 1
    assert health['encrypted_at_rest'] is True

    bundle = tmp_path / 'profile.json'
    bundle.write_text(json.dumps({'memory_items': [], 'unknown': []}), encoding='utf-8')
    preview = client.get('/profile/import/preview', params={'path': str(bundle)})
    assert preview.status_code == 200
    assert preview.json()['ok'] is True
    assert 'unknown' in preview.json()['unknown_tables']


def test_identity_public_export_requires_approval_then_omits_private_key():
    _reset_product_state()
    blocked = client.get('/identity/export')
    assert blocked.status_code == 403
    assert list_guardian_events()[0]['action'] == 'IDENTITY_EXPORT'

    approved = client.get('/identity/export', params={'approved': True})
    assert approved.status_code == 200
    body = approved.json()
    assert body['private_key_exported'] is False
    assert body['public_attestation']['fingerprint']


def test_external_agent_mediation_scaffold():
    _reset_product_state()
    status = client.get('/external-agents/status').json()
    assert status['configured_count'] >= 1
    assert status['agents'][0]['name'] == 'Victor'
    created = client.post('/external-agents', json={'name': 'Research Agent', 'platform': 'Browser', 'scope': 'personal', 'allowed_actions': ['summarize'], 'approval_requirements': ['before_paste']})
    assert created.status_code == 200
    assert created.json()['connected'] is False


def test_helper_plans_for_operator_file_app_and_url():
    assert plan_from_text('prepare my work session')['signature'] == 'daily:operator'
    assert plan_from_text('open app Notes')['signature'] == 'open_app:os'
    assert plan_from_text('open https://github.com/Hetul803/AURA')['signature'] == 'open_url:browser'
    note = plan_from_text('create note: AURA is ready', context={'workspace_hint': '/tmp/aura'})
    assert note['signature'] == 'file:note'
    assert note['steps'][0].action_type == 'FS_WRITE_TEXT'
