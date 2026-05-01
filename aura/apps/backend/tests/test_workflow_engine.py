from fastapi.testclient import TestClient

from api.main import app
from aura.state import db_conn
from aura.workflow_engine import (
    create_workflow_version,
    create_workflow,
    delete_workflow,
    list_workflows,
    list_workflow_repairs,
    list_workflow_versions,
    record_workflow_repair,
    render_workflow_command,
    suggested_workflow_templates,
    update_workflow,
    workflow_update_suggestions,
)
from storage.db import init_db

client = TestClient(app)


def _clear_workflows():
    init_db()
    with db_conn() as conn:
        conn.execute('DELETE FROM workflow_templates')
        conn.execute('DELETE FROM workflow_memory')


def test_workflow_crud_and_render():
    _clear_workflows()
    workflow = create_workflow(
        name='Clone current repo',
        command_template='Clone this repo locally into {folder}',
        trigger_type='context',
        trigger_value='github_repo',
        confidence=0.8,
        metadata={'surface': 'desktop'},
    )

    assert workflow['enabled'] is True
    assert workflow['metadata']['surface'] == 'desktop'
    assert list_workflows()[0]['workflow_id'] == workflow['workflow_id']

    rendered = render_workflow_command(workflow['workflow_id'], {'folder': 'Projects'})
    assert rendered['command'] == 'Clone this repo locally into Projects'

    updated = update_workflow(workflow['workflow_id'], enabled=False, description='disabled for test')
    assert updated['enabled'] is False
    assert list_workflows() == []
    assert list_workflows(include_disabled=True)[0]['description'] == 'disabled for test'

    assert delete_workflow(workflow['workflow_id']) is True


def test_workflow_versions_are_created_and_archived_on_update():
    _clear_workflows()
    workflow = create_workflow(
        name='Clone current repo',
        command_template='Clone this repo locally',
        required_context=['browser_url:github_repo'],
        safety_class='high',
    )

    versions = list_workflow_versions(workflow['workflow_id'])
    assert versions[0]['version'] == 1
    assert versions[0]['required_context'] == ['browser_url:github_repo']

    updated = update_workflow(
        workflow['workflow_id'],
        command_template='Clone this repo locally into {folder}',
        required_context=['browser_url:github_repo', 'workspace_folder'],
        changelog='Add target folder variable',
    )

    assert updated['active_version'] == 2
    versions = list_workflow_versions(workflow['workflow_id'])
    assert versions[0]['version'] == 2
    assert versions[0]['archived'] is False
    assert versions[1]['archived'] is True


def test_workflow_repair_records_trigger_update_suggestion():
    _clear_workflows()
    workflow = create_workflow(name='Reply', command_template='Reply to this email')

    first = record_workflow_repair(workflow['workflow_id'], failed_step='paste', failure_reason='target drift', repair_summary='revalidated target', repair_succeeded=False)
    second = record_workflow_repair(workflow['workflow_id'], failed_step='paste', failure_reason='target drift again', repair_summary='user pasted manually', repair_succeeded=False)

    repairs = list_workflow_repairs(workflow['workflow_id'])
    suggestions = workflow_update_suggestions(workflow['workflow_id'])

    assert first['repair_id']
    assert second['update_recommended'] is True
    assert len(repairs) == 2
    assert suggestions[0]['suggestion'] == 'create_revised_version'


def test_create_workflow_version_manual_contract():
    _clear_workflows()
    workflow = create_workflow(name='Coding worker', command_template='Create a full app for this idea')
    version = create_workflow_version(
        workflow['workflow_id'],
        command_template='Create a full app for this idea in {workspace}',
        steps=[{'action_type': 'AGENT_DELEGATE'}],
        linked_memories=['mem_1'],
        changelog='Add workspace slot',
    )

    assert version['version'] == 2
    assert version['steps'][0]['action_type'] == 'AGENT_DELEGATE'
    assert version['linked_memories'] == ['mem_1']


def test_suggested_workflows_from_learning_memory():
    _clear_workflows()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO workflow_memory(task_type, pattern_key, strategy, confidence, success_count, failure_count, notes)
            VALUES(?,?,?,?,?,?,?)
            ''',
            ('assist:writing', 'task_kind:reply', 'capture_draft_approve_paste', 0.82, 3, 0, 'reply worked'),
        )

    suggestions = suggested_workflow_templates()
    assert suggestions
    assert suggestions[0]['command_template'] == 'Draft a reply to this'
    assert suggestions[0]['source'] == 'learning_suggestion'


def test_workflow_api_contracts():
    _clear_workflows()
    created = client.post('/workflows', json={
        'name': 'Morning inbox',
        'command_template': 'Summarize unread emails',
        'trigger_type': 'schedule',
        'trigger_value': 'morning',
    })
    assert created.status_code == 200
    workflow_id = created.json()['workflow_id']

    listed = client.get('/workflows')
    assert listed.status_code == 200
    assert listed.json()[0]['workflow_id'] == workflow_id

    rendered = client.post(f'/workflows/{workflow_id}/render', json={'variables': {}})
    assert rendered.status_code == 200
    assert rendered.json()['command'] == 'Summarize unread emails'

    patched = client.patch(f'/workflows/{workflow_id}', json={'enabled': False})
    assert patched.status_code == 200
    assert patched.json()['enabled'] is False

    assert client.get('/workflows', params={'include_disabled': True}).json()[0]['workflow_id'] == workflow_id
    assert client.delete(f'/workflows/{workflow_id}').status_code == 200
    assert client.get(f'/workflows/{workflow_id}').status_code == 404


def test_workflow_run_replays_rendered_command():
    _clear_workflows()
    created = client.post('/workflows', json={
        'name': 'Reply workflow',
        'command_template': 'Reply to this email',
        'trigger_type': 'manual',
        'trigger_value': 'reply',
    }).json()

    replay = client.post(f"/workflows/{created['workflow_id']}/run", json={
        'context': {
            'active_app': 'Chrome',
            'browser_url': 'https://mail.google.com/mail/u/0/#inbox/abc',
            'selected_text': 'Can you send the report by 5 PM today?',
        },
    })

    assert replay.status_code == 200
    body = replay.json()
    assert body['rendered_command'] == 'Reply to this email'
    assert body['workflow']['workflow_id'] == created['workflow_id']
    assert body['status'] == 'awaiting_approval'


def test_workflow_version_and_repair_api_contracts():
    _clear_workflows()
    created = client.post('/workflows', json={
        'name': 'Clone current repo',
        'command_template': 'Clone this repo locally',
        'required_context': ['browser_url:github_repo'],
        'safety_class': 'high',
    }).json()
    workflow_id = created['workflow_id']

    versions = client.get(f'/workflows/{workflow_id}/versions')
    assert versions.status_code == 200
    assert versions.json()[0]['version'] == 1

    repair = client.post(f'/workflows/{workflow_id}/repairs', json={
        'failed_step': 'clone',
        'failure_reason': 'folder exists',
        'repair_summary': 'ask for new folder',
        'repair_succeeded': False,
    })
    assert repair.status_code == 200
    assert repair.json()['failure_reason'] == 'folder exists'

    suggestions = client.get(f'/workflows/{workflow_id}/update-suggestions')
    assert suggestions.status_code == 200
