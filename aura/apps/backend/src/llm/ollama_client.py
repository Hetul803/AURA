from __future__ import annotations

import json
import os
from typing import Any

import httpx

DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_TIMEOUT = 20.0


def ollama_host() -> str:
    return os.getenv('OLLAMA_HOST', DEFAULT_HOST).rstrip('/')


def _timeout(value: float | None = None) -> float:
    if value is not None:
        return value
    try:
        return float(os.getenv('OLLAMA_TIMEOUT_SECONDS', str(DEFAULT_TIMEOUT)))
    except ValueError:
        return DEFAULT_TIMEOUT


def ollama_tags(timeout: float | None = None) -> list[dict[str, Any]]:
    host = ollama_host()
    with httpx.Client(timeout=_timeout(timeout)) as client:
        response = client.get(f'{host}/api/tags')
        response.raise_for_status()
        payload = response.json()
    return list(payload.get('models', []))


def ollama_status(timeout: float | None = None) -> dict[str, Any]:
    host = ollama_host()
    try:
        tags = ollama_tags(timeout=timeout)
        return {
            'ok': True,
            'host': host,
            'reachable': True,
            'error': None,
            'detail': None,
            'models': [model.get('name') for model in tags if model.get('name')],
        }
    except httpx.TimeoutException as exc:
        return {
            'ok': False,
            'host': host,
            'reachable': False,
            'error': 'ollama_timeout',
            'detail': str(exc),
            'models': [],
        }
    except httpx.HTTPStatusError as exc:
        return {
            'ok': False,
            'host': host,
            'reachable': False,
            'error': 'ollama_http_error',
            'detail': exc.response.text,
            'models': [],
        }
    except httpx.ConnectError as exc:
        return {
            'ok': False,
            'host': host,
            'reachable': False,
            'error': 'ollama_unreachable',
            'detail': str(exc),
            'models': [],
        }
    except Exception as exc:
        return {
            'ok': False,
            'host': host,
            'reachable': False,
            'error': 'ollama_unavailable',
            'detail': str(exc),
            'models': [],
        }


def ollama_available() -> bool:
    return bool(ollama_status(timeout=0.8).get('ok'))


def default_ollama_model() -> str:
    configured = os.getenv('AURA_ASSIST_MODEL') or os.getenv('OLLAMA_MODEL') or os.getenv('DEFAULT_MODEL')
    if configured:
        return configured
    status = ollama_status(timeout=1.2)
    if status.get('ok') and status.get('models'):
        return status['models'][0]
    return 'qwen2.5:3b'


def ollama_model_present(model_name: str) -> bool:
    if not model_name:
        return False
    status = ollama_status(timeout=1.0)
    return bool(status.get('ok') and model_name in status.get('models', []))


def ollama_generate(*, prompt: str, model: str | None = None, system: str | None = None,
                    format_json: bool = False, timeout: float | None = None,
                    options: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_model = model or default_ollama_model()
    payload: dict[str, Any] = {
        'model': resolved_model,
        'prompt': prompt,
        'stream': False,
        'options': {
            'temperature': 0.2,
            'top_p': 0.9,
            **(options or {}),
        },
    }
    if system:
        payload['system'] = system
    if format_json:
        payload['format'] = 'json'

    host = ollama_host()
    try:
        with httpx.Client(timeout=_timeout(timeout)) as client:
            response = client.post(f'{host}/api/generate', json=payload)
            response.raise_for_status()
            body = response.json()
    except httpx.TimeoutException as exc:
        return {
            'ok': False,
            'provider': 'ollama',
            'model': resolved_model,
            'error': 'ollama_timeout',
            'detail': str(exc),
        }
    except httpx.HTTPError as exc:
        detail = exc.response.text if getattr(exc, 'response', None) is not None else str(exc)
        return {
            'ok': False,
            'provider': 'ollama',
            'model': resolved_model,
            'error': 'ollama_http_error',
            'detail': detail,
        }
    except Exception as exc:
        return {
            'ok': False,
            'provider': 'ollama',
            'model': resolved_model,
            'error': 'ollama_unavailable',
            'detail': str(exc),
        }

    text = str(body.get('response', '')).strip()
    return {
        'ok': True,
        'provider': 'ollama',
        'model': resolved_model,
        'response': text,
        'raw': body,
    }


def parse_json_response(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if not candidate:
        raise ValueError('empty_model_response')
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find('{')
        end = candidate.rfind('}')
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(candidate[start:end + 1])
