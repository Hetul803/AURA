from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RiskLevel = Literal['low', 'medium', 'high', 'critical', 'blocked']


@dataclass(frozen=True)
class ToolSpec:
    action_type: str
    tool: str
    name: str
    description: str
    risk_level: RiskLevel
    requires_approval: bool = False
    permissions: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    device_adapters: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    observation_schema: dict[str, Any] = field(default_factory=dict)
    rollback: str | None = None
    audit: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _spec(
    action_type: str,
    tool: str,
    name: str,
    description: str,
    risk_level: RiskLevel,
    *,
    requires_approval: bool = False,
    permissions: list[str] | None = None,
    side_effects: list[str] | None = None,
    device_adapters: list[str] | None = None,
    input_schema: dict[str, Any] | None = None,
    observation_schema: dict[str, Any] | None = None,
    rollback: str | None = None,
    audit: bool = True,
) -> ToolSpec:
    return ToolSpec(
        action_type=action_type,
        tool=tool,
        name=name,
        description=description,
        risk_level=risk_level,
        requires_approval=requires_approval,
        permissions=permissions or [],
        side_effects=side_effects or [],
        device_adapters=device_adapters or ['desktop-local'],
        input_schema=input_schema or {},
        observation_schema=observation_schema or {},
        rollback=rollback,
        audit=audit,
    )


_TOOLS: dict[str, ToolSpec] = {
    'NOOP': _spec('NOOP', 'control', 'No operation', 'Record an intentional no-op step.', 'low', audit=False),
    'WAIT_FOR': _spec('WAIT_FOR', 'control', 'Wait', 'Pause execution until an external condition or user action.', 'low'),
    'OS_GET_ACTIVE_CONTEXT': _spec(
        'OS_GET_ACTIVE_CONTEXT', 'os', 'Capture active desktop context', 'Read active app, window, browser, clipboard, and selection signals when available.', 'medium',
        permissions=['desktop_context'], side_effects=[], device_adapters=['desktop-local'],
    ),
    'OS_READ_CLIPBOARD': _spec('OS_READ_CLIPBOARD', 'os', 'Read clipboard', 'Read current clipboard text.', 'medium', permissions=['clipboard_read']),
    'OS_WRITE_CLIPBOARD': _spec('OS_WRITE_CLIPBOARD', 'os', 'Write clipboard', 'Write text to the clipboard.', 'medium', permissions=['clipboard_write'], side_effects=['clipboard_changed'], rollback='Restore previous clipboard when captured.'),
    'OS_COPY_SELECTION': _spec('OS_COPY_SELECTION', 'os', 'Copy selection', 'Copy currently selected text from the active app.', 'medium', permissions=['keyboard_control', 'clipboard_write'], side_effects=['clipboard_changed']),
    'OS_PASTE': _spec('OS_PASTE', 'os', 'Paste into active app', 'Paste text into the active app or focused field.', 'high', requires_approval=True, permissions=['keyboard_control', 'clipboard_write'], side_effects=['active_app_modified'], rollback='User can undo in the target app when supported.'),
    'OS_TYPE_TEXT': _spec('OS_TYPE_TEXT', 'os', 'Type text', 'Type text into the active app.', 'high', requires_approval=True, permissions=['keyboard_control'], side_effects=['active_app_modified']),
    'OS_PRESS_KEYS': _spec('OS_PRESS_KEYS', 'os', 'Press keys', 'Send keyboard shortcuts to the active app.', 'high', requires_approval=True, permissions=['keyboard_control'], side_effects=['active_app_modified']),
    'OS_OPEN_APP': _spec('OS_OPEN_APP', 'os', 'Open app', 'Open a local application.', 'medium', permissions=['app_launch'], side_effects=['app_opened']),
    'OS_ACTIVATE_APP': _spec('OS_ACTIVATE_APP', 'os', 'Activate app', 'Bring a local application to the foreground.', 'medium', permissions=['app_control'], side_effects=['focus_changed']),
    'OS_OPEN_PATH': _spec('OS_OPEN_PATH', 'os', 'Open path', 'Open a local file or folder path.', 'medium', permissions=['filesystem_read', 'app_launch'], side_effects=['app_opened']),
    'OS_OPEN_FILE': _spec('OS_OPEN_FILE', 'os', 'Open file', 'Open a local file.', 'medium', permissions=['filesystem_read', 'app_launch'], side_effects=['app_opened']),
    'OS_OPEN_FOLDER': _spec('OS_OPEN_FOLDER', 'os', 'Open folder', 'Open a local folder.', 'medium', permissions=['filesystem_read', 'app_launch'], side_effects=['app_opened']),
    'OS_OPEN_URL': _spec('OS_OPEN_URL', 'browser', 'Open URL', 'Open a URL in the browser.', 'medium', permissions=['browser_open'], side_effects=['network_navigation'], device_adapters=['desktop-local', 'browser-visible']),
    'WEB_NAVIGATE': _spec('WEB_NAVIGATE', 'browser', 'Navigate browser', 'Navigate a browser page to a URL.', 'medium', permissions=['browser_control'], side_effects=['network_navigation'], device_adapters=['browser-visible']),
    'WEB_CLICK': _spec('WEB_CLICK', 'browser', 'Click page element', 'Click an element on a browser page.', 'high', requires_approval=False, permissions=['browser_control'], side_effects=['page_state_changed'], device_adapters=['browser-visible']),
    'WEB_TYPE': _spec('WEB_TYPE', 'browser', 'Type into page', 'Type text into a browser field.', 'high', requires_approval=True, permissions=['browser_control'], side_effects=['page_state_changed'], device_adapters=['browser-visible']),
    'WEB_READ': _spec('WEB_READ', 'browser', 'Read page', 'Read visible page content.', 'medium', permissions=['browser_read'], device_adapters=['browser-visible']),
    'WEB_UPLOAD': _spec('WEB_UPLOAD', 'browser', 'Upload file', 'Upload a local file through the browser.', 'high', requires_approval=True, permissions=['browser_control', 'filesystem_read'], side_effects=['file_shared'], device_adapters=['browser-visible']),
    'FS_EXISTS': _spec('FS_EXISTS', 'filesystem', 'Check path exists', 'Check whether a local filesystem path exists.', 'low', permissions=['filesystem_read']),
    'FS_READ_TEXT': _spec('FS_READ_TEXT', 'filesystem', 'Read text file', 'Read a local text file.', 'medium', permissions=['filesystem_read']),
    'FS_WRITE_TEXT': _spec('FS_WRITE_TEXT', 'filesystem', 'Write text file', 'Write text to a local file.', 'high', requires_approval=True, permissions=['filesystem_write'], side_effects=['file_modified'], rollback='Use file snapshots or version control when available.'),
    'CODE_RUN': _spec('CODE_RUN', 'code', 'Run command', 'Run a shell command in a local workspace.', 'high', permissions=['shell_execute', 'filesystem_read', 'filesystem_write'], side_effects=['process_started', 'files_may_change', 'network_possible'], rollback='Depends on command; prefer version control before risky changes.'),
    'CODE_REPAIR': _spec('CODE_REPAIR', 'code', 'Repair code run', 'Run a local repair command or retry strategy.', 'high', permissions=['shell_execute', 'filesystem_write'], side_effects=['files_may_change']),
    'AGENT_DELEGATE': _spec('AGENT_DELEGATE', 'agent', 'Delegate to agent router', 'Ask AURA to route work to the best worker and prepare a self-contained agent prompt.', 'medium', permissions=['agent_route'], side_effects=['agent_task_created'], device_adapters=['desktop-local', 'enterprise-workspace']),
    'USER_AI_PREPARE_PROMPT': _spec('USER_AI_PREPARE_PROMPT', 'agent', 'Prepare user AI prompt', 'Build a prompt for the user-owned ChatGPT or Claude web session.', 'medium', permissions=['desktop_context', 'browser_open'], side_effects=['prompt_prepared'], device_adapters=['desktop-local', 'browser-visible']),
    'TAKE_SCREENSHOT': _spec('TAKE_SCREENSHOT', 'os', 'Take screenshot', 'Capture the current screen.', 'medium', permissions=['screen_capture'], side_effects=['screenshot_created']),
    'CLIPBOARD_COPY': _spec('CLIPBOARD_COPY', 'os', 'Copy to clipboard', 'Compatibility alias for copying text to clipboard.', 'medium', permissions=['clipboard_write'], side_effects=['clipboard_changed']),
    'CLIPBOARD_PASTE': _spec('CLIPBOARD_PASTE', 'os', 'Paste clipboard', 'Compatibility alias for paste into active app.', 'high', requires_approval=True, permissions=['keyboard_control', 'clipboard_write'], side_effects=['active_app_modified']),
    'ASSIST_CAPTURE_CONTEXT': _spec('ASSIST_CAPTURE_CONTEXT', 'assist', 'Capture assist context', 'Capture context for assistive writing or summarization.', 'medium', permissions=['desktop_context']),
    'ASSIST_RESEARCH_CONTEXT': _spec('ASSIST_RESEARCH_CONTEXT', 'assist', 'Research context', 'Research or summarize captured context.', 'medium', permissions=['llm_call']),
    'ASSIST_DRAFT': _spec('ASSIST_DRAFT', 'assist', 'Draft response', 'Draft text from context using the selected model.', 'medium', permissions=['llm_call']),
    'ASSIST_WAIT_APPROVAL': _spec('ASSIST_WAIT_APPROVAL', 'assist', 'Wait for assist approval', 'Pause for user approval before paste/send workflow continues.', 'low'),
    'ASSIST_PASTE_BACK': _spec('ASSIST_PASTE_BACK', 'assist', 'Paste approved draft', 'Paste an approved draft back into the active app.', 'high', requires_approval=True, permissions=['keyboard_control', 'clipboard_write'], side_effects=['active_app_modified']),
}


def list_tool_specs() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in _TOOLS.values()]


def get_tool_spec(action_type: str) -> dict[str, Any] | None:
    spec = _TOOLS.get(action_type)
    return spec.to_dict() if spec else None


def require_tool_spec(action_type: str) -> dict[str, Any]:
    spec = get_tool_spec(action_type)
    if not spec:
        raise KeyError(action_type)
    return spec


def is_registered_action(action_type: str) -> bool:
    return action_type in _TOOLS


def requires_tool_approval(action_type: str) -> bool:
    spec = get_tool_spec(action_type)
    return bool(spec and spec['requires_approval'])


def risk_for_action(action_type: str) -> RiskLevel:
    spec = get_tool_spec(action_type)
    return spec['risk_level'] if spec else 'blocked'


def actions_for_device(adapter_id: str) -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in _TOOLS.values() if adapter_id in spec.device_adapters]
