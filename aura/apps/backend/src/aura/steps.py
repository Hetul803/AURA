from __future__ import annotations
from pydantic import BaseModel
from typing import Any, Literal

ActionType = Literal['OS_OPEN_APP','OS_OPEN_URL','WEB_NAVIGATE','WEB_CLICK','WEB_TYPE','WEB_READ','SCREENSHOT','CLIPBOARD_COPY','CLIPBOARD_PASTE','WAIT_FOR','NOOP']
SafetyLevel = Literal['SAFE','CONFIRM','BLOCKED']

class Condition(BaseModel):
    type: str
    key: str
    expected: Any

class RecoveryStrategy(BaseModel):
    type: str
    args: dict[str, Any] = {}

class RetryPolicy(BaseModel):
    max_retries: int = 1
    backoff_ms: int = 100

class Step(BaseModel):
    id: str
    name: str
    action_type: ActionType
    args: dict[str, Any] = {}
    preconditions: list[Condition] = []
    postconditions: list[Condition] = []
    safety_level: SafetyLevel = 'SAFE'
    retry_policy: RetryPolicy = RetryPolicy()
    recovery: list[RecoveryStrategy] = []
