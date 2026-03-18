from pathlib import Path
from tempfile import TemporaryDirectory

from aura.planner import plan_from_text



def test_cursor_demo_intent_plans_os_steps():
    plan = plan_from_text('Open Cursor and paste this website prompt: build a modern website')
    assert plan['goal']
    assert plan['steps'][0].action_type == 'OS_OPEN_APP'
    assert plan['steps'][0].tool == 'os'



def test_selected_text_flow_plans_copy_then_search():
    plan = plan_from_text('Take the selected text, search it, and give me key points.')
    assert plan['steps'][0].action_type == 'OS_COPY_SELECTION'
    assert plan['steps'][1].action_type == 'WEB_READ'
    assert plan['success_criteria']



def test_code_plan_is_structured():
    with TemporaryDirectory() as td:
        script = Path(td) / 'demo.py'
        script.write_text("pritn('hello')\n", encoding='utf-8')
        plan = plan_from_text(f'fix and run python script at "{script}"')
        assert plan['signature'] == 'code:python_script'
        assert plan['context']['script_path'] == str(script)
        assert plan['steps'][1].fallback_hint == 'repair_python_and_retry'
