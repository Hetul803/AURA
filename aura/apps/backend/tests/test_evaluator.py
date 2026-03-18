from aura.evaluator import evaluate_step
from aura.repair import strategy_for_failure
from aura.steps import Step



def test_evaluator_selects_auto_repair_for_name_error():
    step = Step(id='s1', name='Run python script', action_type='CODE_RUN', tool='code', expected_outcome={'exit_code': 0}, fallback_hint='repair_python_and_retry')
    result = {'ok': False, 'retryable': True, 'error': 'pritn'}
    observation = {'failure_class': 'name_error', 'failure_detail': 'pritn', 'exit_code': 1}
    decision = evaluate_step(step, result, observation, {'failure_history': [], 'repair_attempts': {}, 'total_repairs': 0})
    assert decision['outcome'] == 'repair'
    assert decision['strategy'] == 'repair_python_name'



def test_evaluator_stops_on_identical_failure_loop():
    step = Step(id='s1', name='Run python script', action_type='CODE_RUN', tool='code', expected_outcome={'exit_code': 0}, fallback_hint='repair_python_and_retry')
    result = {'ok': False, 'retryable': True, 'error': 'pritn'}
    observation = {'failure_class': 'name_error', 'failure_detail': 'pritn', 'exit_code': 1}
    signature = 'CODE_RUN|name_error|pritn|pritn'
    decision = evaluate_step(step, result, observation, {
        'failure_history': [{'signature': signature}, {'signature': signature}],
        'repair_attempts': {'s1': 1},
        'total_repairs': 1,
    })
    assert decision['outcome'] == 'stop'
    assert decision['reason'] == 'identical_failure_repeated'



def test_repair_strategy_marks_dependency_errors_for_user_escalation():
    strategy = strategy_for_failure('dependency_error')
    assert strategy.escalate_to_user
    assert not strategy.auto_repair
