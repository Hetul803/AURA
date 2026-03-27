import threading, time
from aura.executor import execute_steps
from aura.steps import Step
from aura.state import cancel_run


def test_panic_cancels_wait_step_quickly():
    events = []
    run_id = 'panic-test'
    steps = [Step(id='w1', name='wait', action_type='WAIT_FOR', args={'ms': 5000})]

    def worker():
        execute_steps(run_id, steps, lambda e: events.append(e), wait_poll_ms=100)

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.2)
    cancel_run(run_id)
    t.join(timeout=1.0)
    assert not t.is_alive()
    assert any(e.get('type') == 'run_cancelled' for e in events)
