from aura import executor
from aura.orchestrator import approve_run, reject_run
from aura.safety import requires_confirmation
from aura.state import db_conn, get_run_context, list_audit_log, list_run_events, set_run_context
from aura.steps import Step
from storage.db import init_db
from tools.tool_result import success

def test_sensitive_detection():
    assert requires_confirmation('send email now')
    assert not requires_confirmation('open gmail')


def _clear_durable_tables():
    init_db()
    with db_conn() as conn:
        for table in ['run_records', 'run_events', 'approval_records', 'audit_log', 'reflection_records', 'workflow_memory', 'preference_memory', 'site_memory', 'safety_memory']:
            conn.execute(f'DELETE FROM {table}')


def _confirmation_run(run_id: str, step: Step):
    set_run_context(run_id, {
        'text': 'test confirmation gate',
        'choices': {},
        'use_macro': False,
        'steps': [step.model_dump()],
        'plan': {'signature': 'test:confirmation', 'goal': 'prove confirmation gate', 'steps': [step.model_dump()]},
        'current_step_index': 0,
        'last_observation': {},
        'status': 'running',
        'failure_history': [],
        'repair_history': [],
        'repair_attempts': {},
        'total_repairs': 0,
        'terminal_outcome': None,
        'step_history': [],
        'safety_history': [],
        'learning': {},
        'approval_state': {'required': False, 'status': 'not_requested'},
    })


def test_confirm_step_pauses_before_dispatch_and_resumes_after_approval(monkeypatch):
    _clear_durable_tables()
    run_id = 'confirm-gate-test'
    step = Step(
        id='confirm-1',
        name='Write clipboard after confirmation',
        action_type='OS_WRITE_CLIPBOARD',
        tool='os',
        args={'text': 'approved text'},
        expected_outcome={'written_gte': 5},
        safety_level='CONFIRM',
    )
    _confirmation_run(run_id, step)
    calls = []
    events = []

    def fake_dispatch(step_to_run, run_context=None):
        calls.append(step_to_run.action_type)
        return success(step_to_run.action_type, result={'written': len(step_to_run.args['text'])}, observation={'clipboard_length': len(step_to_run.args['text'])})

    monkeypatch.setattr(executor, 'dispatch_tool_action', fake_dispatch)

    first = executor.execute_steps(run_id, [step], lambda e: events.append(e))

    assert first[-1]['status'] == 'awaiting_approval'
    assert calls == []
    state = get_run_context(run_id)
    assert state['status'] == 'awaiting_approval'
    assert state['approval_state']['kind'] == 'tool_confirmation'
    assert state['approval_state']['status'] == 'pending'
    assert any(e['type'] == 'approval_required' for e in events)

    approved = approve_run(run_id, event_cb=lambda e: events.append(e))

    assert approved['ok'] is True
    assert calls == ['OS_WRITE_CLIPBOARD']
    assert get_run_context(run_id)['status'] == 'done'
    assert any(e['event_type'] == 'approval_required' for e in list_run_events(run_id))
    audit_types = [row['event_type'] for row in list_audit_log(run_id=run_id)]
    assert 'approval_requested' in audit_types
    assert 'approval_approved' in audit_types


def test_confirm_step_reject_stops_without_dispatch(monkeypatch):
    _clear_durable_tables()
    run_id = 'confirm-reject-test'
    step = Step(
        id='confirm-2',
        name='Paste after confirmation',
        action_type='OS_PASTE',
        tool='os',
        args={'text': 'do not paste'},
        expected_outcome={'pasted_gte': 1},
        safety_level='CONFIRM',
    )
    _confirmation_run(run_id, step)
    calls = []

    monkeypatch.setattr(executor, 'dispatch_tool_action', lambda step_to_run, run_context=None: calls.append(step_to_run.action_type) or success(step_to_run.action_type, result={'pasted': 1}))

    first = executor.execute_steps(run_id, [step], lambda e: None)
    rejected = reject_run(run_id, reason='not safe yet')

    assert first[-1]['status'] == 'awaiting_approval'
    assert rejected['status'] == 'rejected'
    assert calls == []
    assert get_run_context(run_id)['terminal_outcome'] == 'rejected'
    audit_types = [row['event_type'] for row in list_audit_log(run_id=run_id)]
    assert 'approval_requested' in audit_types
    assert 'approval_rejected' in audit_types
