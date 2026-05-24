from __future__ import annotations

import json
import os
import platform
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from .branding import get_brand
from .licensing import license_status
from .state import record_audit_event


SECRET_PATTERNS = [
    (re.compile(r'sk_(live|test)_[A-Za-z0-9_]+'), 'sk_[redacted]'),
    (re.compile(r'(?i)(password|api[_-]?key|token|secret)["\':=\s]+[^"\',\s}]+'), r'\1=[redacted]'),
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.S), '[redacted_private_key]'),
]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if re.search(r'(?i)(password|api[_-]?key|token|secret|private[_-]?key)', key_text):
                redacted[key_text] = '[redacted]'
            else:
                redacted[key_text] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value[:200]]
    if isinstance(value, str):
        redacted = value
        for pattern, replacement in SECRET_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted[:8000]
    return value


def _license_server() -> str:
    return (os.getenv('AURA_LICENSE_SERVER_URL') or '').rstrip('/')


def _update_feed_url() -> str:
    explicit = (os.getenv('AURA_UPDATE_FEED_URL') or '').strip()
    if explicit:
        return explicit
    server = _license_server()
    return f'{server}/api/updates/latest' if server else ''


def launch_status() -> dict[str, Any]:
    brand = get_brand()
    update_url = _update_feed_url()
    crash_url = (os.getenv('AURA_CRASH_REPORT_URL') or '').strip() or (f'{_license_server()}/api/crash-reports' if _license_server() else '')
    return {
        'ok': True,
        'checked_at': _now(),
        'brand': {
            'product_name': brand.get('product_name'),
            'company_name': brand.get('company_name'),
            'download_url': brand.get('download_url'),
        },
        'license': license_status(),
        'launch_services': {
            'license_server_configured': bool(_license_server()),
            'license_server_url': _license_server() or None,
            'update_feed_configured': bool(update_url),
            'update_feed_url': update_url or None,
            'crash_reporting_configured': bool(crash_url),
            'crash_report_url': crash_url or None,
        },
        'system': {
            'platform': platform.system(),
            'release': platform.release(),
            'machine': platform.machine(),
        },
    }


def check_for_updates(current_version: str = '1.0.0', platform_name: str | None = None, arch: str | None = None) -> dict[str, Any]:
    feed = _update_feed_url()
    if not feed:
        brand = get_brand()
        return {
            'ok': False,
            'status': 'update_feed_not_configured',
            'message': 'Set AURA_UPDATE_FEED_URL or AURA_LICENSE_SERVER_URL to enable update checks. Manual DMG updates still work.',
            'current_version': current_version,
            'download_url': brand.get('download_url') or None,
        }
    try:
        response = httpx.get(
            feed,
            params={
                'version': current_version,
                'platform': platform_name or ('darwin' if platform.system() == 'Darwin' else platform.system().lower()),
                'arch': arch or platform.machine(),
            },
            timeout=6,
        )
        data = response.json()
        return {'ok': response.is_success, 'status_code': response.status_code, 'feed_url': feed, **data}
    except Exception as exc:
        return {
            'ok': False,
            'status': 'update_feed_unreachable',
            'message': f'Update feed could not be reached: {exc}',
            'feed_url': feed,
            'current_version': current_version,
        }


def report_crash(payload: dict[str, Any]) -> dict[str, Any]:
    crash_url = (os.getenv('AURA_CRASH_REPORT_URL') or '').strip() or (f'{_license_server()}/api/crash-reports' if _license_server() else '')
    report = {
        'product': get_brand().get('product_name') or 'AURA',
        'reported_at': _now(),
        'system': {
            'platform': platform.system(),
            'release': platform.release(),
            'machine': platform.machine(),
        },
        'payload': _redact(payload or {}),
    }
    record_audit_event({
        'event_type': 'crash_report_prepared',
        'action_type': 'CRASH_REPORT',
        'risk_level': 'low',
        'message': 'Prepared redacted crash/error report.',
        'payload': {'configured': bool(crash_url), 'source': report['payload'].get('source')},
    })
    if not crash_url:
        return {
            'ok': False,
            'status': 'crash_reporting_not_configured',
            'message': 'Crash report was redacted locally. Set AURA_CRASH_REPORT_URL or AURA_LICENSE_SERVER_URL to upload reports.',
            'report': report,
        }
    try:
        response = httpx.post(crash_url, json=report, timeout=6)
        try:
            remote = response.json()
        except Exception:
            remote = {'text': response.text[:1000]}
        return {'ok': response.is_success, 'status_code': response.status_code, 'report': report, 'remote': remote}
    except Exception as exc:
        return {
            'ok': False,
            'status': 'crash_report_upload_failed',
            'message': f'Crash report was redacted locally, but upload failed: {exc}',
            'report': report,
        }


def launch_env_template() -> str:
    return json.dumps({
        'website': {
            'PUBLIC_BASE_URL': 'https://your-domain.com',
            'STRIPE_SECRET_KEY': 'sk_live_...',
            'STRIPE_PRICE_ID': 'price_...',
            'STRIPE_WEBHOOK_SECRET': 'whsec_...',
            'AURA_VENDOR_PRIVATE_KEY': '-----BEGIN PRIVATE KEY-----...',
            'AURA_VENDOR_PUBLIC_KEY': '-----BEGIN PUBLIC KEY-----...',
            'AURA_ADMIN_TOKEN': 'generate-a-long-random-token',
            'AURA_DOWNLOAD_MAC_URL': 'https://your-domain.com/downloads/AURA-1.0.0-mac-arm64.dmg',
        },
        'desktop_backend': {
            'AURA_LICENSE_PUBLIC_KEY': '-----BEGIN PUBLIC KEY-----...',
            'AURA_LICENSE_SERVER_URL': 'https://your-domain.com',
            'AURA_UPDATE_FEED_URL': 'https://your-domain.com/api/updates/latest',
            'AURA_CRASH_REPORT_URL': 'https://your-domain.com/api/crash-reports',
        },
    }, indent=2)
