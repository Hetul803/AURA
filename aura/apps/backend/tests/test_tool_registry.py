from fastapi.testclient import TestClient

from api.main import app
from aura.safety import guard_step
from aura.steps import Step
from devices.adapters import get_device_adapter, list_device_adapters
from tools.registry import actions_for_device, get_tool_spec, requires_tool_approval, risk_for_action
from tools.tool_router import dispatch_tool_action

client = TestClient(app)


def test_registry_describes_risky_tools():
    code_run = get_tool_spec('CODE_RUN')
    assert code_run is not None
    assert code_run['risk_level'] == 'high'
    assert code_run['requires_approval'] is False
    assert 'shell_execute' in code_run['permissions']
    assert requires_tool_approval('CODE_RUN') is False

    noop = get_tool_spec('NOOP')
    assert noop is not None
    assert noop['risk_level'] == 'low'
    assert risk_for_action('NOOP') == 'low'


def test_registry_drives_safety_confirmation():
    step = Step(
        id='paste',
        name='Paste approved response',
        action_type='OS_PASTE',
        tool='os',
        args={'text': 'hello'},
        safety_level='SAFE',
    )

    assert guard_step(step) == 'confirm'


def test_device_adapters_include_desktop_and_future_surfaces():
    adapters = {item['adapter_id']: item for item in list_device_adapters()}
    assert adapters['desktop-local']['status'] == 'available'
    assert adapters['phone-companion']['status'] == 'planned'
    assert adapters['enterprise-workspace']['status'] == 'planned'
    assert get_device_adapter('desktop-local')['surface'] == 'desktop'

    desktop_actions = {item['action_type'] for item in actions_for_device('desktop-local')}
    assert 'CODE_RUN' in desktop_actions
    assert 'OS_PASTE' in desktop_actions


def test_unknown_action_is_rejected_before_dispatch():
    class UnknownStep:
        action_type = 'UNKNOWN_TOOL'

    result = dispatch_tool_action(UnknownStep())
    assert result['ok'] is False
    assert result['error'] == 'unsupported_action'
    assert result['observation']['registered'] is False


def test_tool_and_device_api_contracts():
    tools = client.get('/tools')
    assert tools.status_code == 200
    assert any(item['action_type'] == 'CODE_RUN' for item in tools.json())

    code_run = client.get('/tools/CODE_RUN')
    assert code_run.status_code == 200
    assert code_run.json()['requires_approval'] is False

    missing_tool = client.get('/tools/UNKNOWN_TOOL')
    assert missing_tool.status_code == 404

    devices = client.get('/devices')
    assert devices.status_code == 200
    assert any(item['adapter_id'] == 'desktop-local' for item in devices.json())

    phone = client.get('/devices/phone-companion')
    assert phone.status_code == 200
    assert phone.json()['surface'] == 'phone'

    desktop_tools = client.get('/tools', params={'device_adapter': 'desktop-local'})
    assert desktop_tools.status_code == 200
    assert any(item['action_type'] == 'OS_PASTE' for item in desktop_tools.json())
