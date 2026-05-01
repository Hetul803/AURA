from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal

ActionType = Literal[
    'OS_OPEN_APP', 'OS_ACTIVATE_APP', 'OS_OPEN_PATH', 'OS_OPEN_FILE', 'OS_OPEN_FOLDER',
    'OS_GET_ACTIVE_CONTEXT', 'OS_READ_CLIPBOARD', 'OS_WRITE_CLIPBOARD', 'OS_PASTE', 'OS_COPY_SELECTION', 'OS_TYPE_TEXT', 'OS_PRESS_KEYS',
    'OS_OPEN_URL', 'WEB_NAVIGATE', 'WEB_CLICK', 'WEB_TYPE', 'WEB_READ', 'WEB_UPLOAD',
    'FS_EXISTS', 'FS_READ_TEXT', 'FS_WRITE_TEXT',
    'CODE_RUN', 'CODE_REPAIR',
    'AGENT_DELEGATE',
    'USER_AI_PREPARE_PROMPT',
    'TAKE_SCREENSHOT', 'CLIPBOARD_COPY', 'CLIPBOARD_PASTE', 'WAIT_FOR', 'NOOP',
    'ASSIST_CAPTURE_CONTEXT', 'ASSIST_RESEARCH_CONTEXT', 'ASSIST_DRAFT', 'ASSIST_WAIT_APPROVAL', 'ASSIST_PASTE_BACK'
]
ToolType = Literal['browser', 'os', 'filesystem', 'code', 'control', 'assist', 'agent']
SafetyLevel = Literal['SAFE', 'CONFIRM', 'BLOCKED']


class Condition(BaseModel):
    type: str
    key: str
    expected: Any


class RecoveryStrategy(BaseModel):
    type: str
    args: dict[str, Any] = Field(default_factory=dict)


class RetryPolicy(BaseModel):
    max_retries: int = 1
    backoff_ms: int = 100


class Step(BaseModel):
    id: str
    name: str
    action_type: ActionType
    tool: ToolType = 'control'
    args: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[Condition] = Field(default_factory=list)
    postconditions: list[Condition] = Field(default_factory=list)
    expected_outcome: dict[str, Any] = Field(default_factory=dict)
    fallback_hint: str | None = None
    safety_level: SafetyLevel = 'SAFE'
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    recovery: list[RecoveryStrategy] = Field(default_factory=list)
