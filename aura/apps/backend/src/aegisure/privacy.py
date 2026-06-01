from __future__ import annotations

import json
import re
from typing import Any


SECRET_PATTERNS = [
    re.compile(r'(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|password|passwd|pwd)\b\s*[:=]\s*["\']?([A-Za-z0-9_\-./+=]{8,})'),
    re.compile(r'(?i)\b(bearer)\s+([A-Za-z0-9_\-./+=]{16,})'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----', re.S),
    re.compile(r'\bsk-[A-Za-z0-9]{20,}\b'),
    re.compile(r'\bgh[pousr]_[A-Za-z0-9_]{20,}\b'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'\b(?:\d[ -]*?){13,19}\b'),
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
]

SENSITIVE_HINTS = {
    'ssn',
    'social security',
    'credit card',
    'card number',
    'bank account',
    'routing number',
    'passport',
    'private key',
    'confidential',
    'company confidential',
    'proprietary',
}

REDACTION = '[REDACTED]'


def detect_secret(text: str | None) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def detect_sensitive(text: str | None) -> bool:
    if not text:
        return False
    lower = text.lower()
    return detect_secret(text) or any(hint in lower for hint in SENSITIVE_HINTS)


def redact_text(text: str | None, *, limit: int | None = None) -> str:
    if text is None:
        return ''
    redacted = str(text)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: f"{m.group(1)}={REDACTION}" if m.groups() and len(m.groups()) >= 2 else REDACTION, redacted)
    if limit is not None and len(redacted) > limit:
        redacted = redacted[:limit] + '\n...[truncated]'
    return redacted


def redact_value(value: Any, *, text_limit: int | None = 4000) -> Any:
    if isinstance(value, str):
        return redact_text(value, limit=text_limit)
    if isinstance(value, list):
        return [redact_value(item, text_limit=text_limit) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item, text_limit=text_limit) for item in value)
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            key_text = str(key)
            if detect_sensitive(key_text):
                out[key] = REDACTION
            else:
                out[key] = redact_value(item, text_limit=text_limit)
        return out
    return value


def safe_json_dumps(value: Any) -> str:
    return json.dumps(redact_value(value), sort_keys=True, default=str)


def sensitivity_labels(text: str | None) -> list[str]:
    labels = []
    if detect_secret(text):
        labels.append('secret')
    if text and any(hint in text.lower() for hint in SENSITIVE_HINTS):
        labels.append('sensitive_personal_or_company_data')
    return labels
