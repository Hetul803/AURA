from aura.steps import Step
from tools.os_automation import handle_os_action
from aura.executor import execute_steps


def test_os_action_wrapper_returns_structured_response():
    step = Step(id='1', name='active', action_type='OS_GET_ACTIVE_CONTEXT', args={})
    out = handle_os_action(step)
    assert 'ok' in out


def test_mixed_os_web_sequence_executes():
    steps = [
        Step(id='1', name='ctx', action_type='OS_GET_ACTIVE_CONTEXT'),
        Step(id='2', name='wait', action_type='WAIT_FOR', args={'ms': 10}),
    ]
    events = []
    res = execute_steps('run-os-mixed', steps, lambda e: events.append(e), wait_poll_ms=5)
    assert len(res) == 2
    assert any(e.get('type') == 'step_status' for e in events)
