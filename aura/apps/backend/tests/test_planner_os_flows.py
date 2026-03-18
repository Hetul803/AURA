from aura.planner import plan_from_text


def test_cursor_demo_intent_plans_os_steps():
    p = plan_from_text('Open Cursor and paste this website prompt: build a modern website')
    assert p['steps'][0].action_type == 'OS_OPEN_APP'


def test_selected_text_flow_plans_copy_then_search():
    p = plan_from_text('Take the selected text, search it, and give me key points.')
    assert p['steps'][0].action_type == 'OS_COPY_SELECTION'
    assert p['steps'][1].action_type == 'WEB_READ'
