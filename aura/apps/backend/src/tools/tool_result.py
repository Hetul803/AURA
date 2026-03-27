from __future__ import annotations

from typing import Any


def make_tool_result(
    *,
    action: str,
    status: str,
    result: dict[str, Any] | None = None,
    observation: dict[str, Any] | None = None,
    error: str | dict[str, Any] | None = None,
    retryable: bool = False,
    requires_user: bool = False,
    safety_flags: list[str] | None = None,
    artifacts: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'ok': status == 'success',
        'status': status,
        'action': action,
        'result': result or {},
        'observation': observation or {},
        'error': error,
        'retryable': retryable,
        'requires_user': requires_user,
        'safety_flags': safety_flags or [],
        'artifacts': artifacts or [],
    }
    if result:
        payload.update(result)
    payload.update(extra)
    return payload


def success(action: str, *, result: dict[str, Any] | None = None, observation: dict[str, Any] | None = None,
            safety_flags: list[str] | None = None, artifacts: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return make_tool_result(
        action=action,
        status='success',
        result=result,
        observation=observation,
        safety_flags=safety_flags,
        artifacts=artifacts,
        **extra,
    )


def failure(action: str, *, error: str | dict[str, Any], observation: dict[str, Any] | None = None,
            retryable: bool = False, requires_user: bool = False,
            safety_flags: list[str] | None = None, artifacts: list[str] | None = None,
            result: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return make_tool_result(
        action=action,
        status='failed',
        result=result,
        observation=observation,
        error=error,
        retryable=retryable,
        requires_user=requires_user,
        safety_flags=safety_flags,
        artifacts=artifacts,
        **extra,
    )
