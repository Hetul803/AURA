from __future__ import annotations

from tools.code_runner import handle_code_action
from tools.filesystem_tool import handle_filesystem_action
from tools.os_automation import handle_os_action
from tools.tool_result import failure
from tools.web_playwright import handle_web_action

OS_ACTIONS = {
    'OS_OPEN_APP', 'OS_ACTIVATE_APP', 'OS_OPEN_PATH', 'OS_OPEN_FILE', 'OS_OPEN_FOLDER',
    'OS_GET_ACTIVE_CONTEXT', 'OS_READ_CLIPBOARD', 'OS_WRITE_CLIPBOARD', 'OS_PASTE',
    'OS_COPY_SELECTION', 'OS_TYPE_TEXT', 'OS_PRESS_KEYS', 'TAKE_SCREENSHOT'
}
WEB_ACTIONS = {'OS_OPEN_URL', 'WEB_NAVIGATE', 'WEB_CLICK', 'WEB_TYPE', 'WEB_READ', 'WEB_UPLOAD', 'NOOP'}
FILESYSTEM_ACTIONS = {'FS_EXISTS', 'FS_READ_TEXT', 'FS_WRITE_TEXT'}
CODE_ACTIONS = {'CODE_RUN', 'CODE_REPAIR'}



def dispatch_tool_action(step) -> dict:
    if step.action_type in OS_ACTIONS:
        return handle_os_action(step)
    if step.action_type in WEB_ACTIONS:
        return handle_web_action(step)
    if step.action_type in FILESYSTEM_ACTIONS:
        return handle_filesystem_action(step)
    if step.action_type in CODE_ACTIONS:
        return handle_code_action(step)
    if step.action_type == 'WAIT_FOR':
        return {'ok': True, 'status': 'success', 'action': 'WAIT_FOR', 'result': {}, 'observation': {}, 'error': None, 'retryable': False, 'requires_user': False, 'safety_flags': [], 'artifacts': []}
    return failure(step.action_type, error='unsupported_action')
