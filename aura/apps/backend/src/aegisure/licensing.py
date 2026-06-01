from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .state import db_conn, record_audit_event


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _device_fingerprint() -> str:
    raw = '|'.join([
        os.uname().sysname if hasattr(os, 'uname') else os.name,
        os.uname().machine if hasattr(os, 'uname') else 'unknown',
        os.getenv('USER') or os.getenv('USERNAME') or 'user',
    ])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]


def configured_public_key() -> str | None:
    raw = os.getenv('AEGISURE_LICENSE_PUBLIC_KEY') or os.getenv('AEGISURE_VENDOR_PUBLIC_KEY')
    if not raw:
        return None
    if raw.strip().startswith('-----BEGIN'):
        return raw
    try:
        return base64.b64decode(raw).decode('utf-8')
    except Exception:
        return raw


def license_status() -> dict[str, Any]:
    row = db_conn().execute('SELECT * FROM license_records ORDER BY verified_at DESC LIMIT 1').fetchone()
    if not row:
        return {
            'status': 'local_free',
            'tier': 'local_free',
            'account_email': None,
            'activated': False,
            'device_fingerprint': _device_fingerprint(),
            'license_public_key_configured': bool(configured_public_key()),
            'message': 'No paid license is active. Aegisure runs in local private-alpha mode.',
        }
    item = dict(row)
    item['features'] = _loads(item.pop('features_json', None), {})
    item['metadata'] = _loads(item.pop('metadata_json', None), {})
    item['activated'] = item.get('status') == 'active'
    item['license_public_key_configured'] = bool(configured_public_key())
    return item


def verify_license_token(token: str) -> dict[str, Any]:
    public_pem = configured_public_key()
    if not public_pem:
        return {
            'ok': False,
            'status': 'license_server_not_configured',
            'message': 'Set AEGISURE_LICENSE_PUBLIC_KEY before activating paid licenses. The app stays in local_free mode.',
        }
    parts = token.strip().split('.')
    if len(parts) != 2:
        return {'ok': False, 'status': 'invalid_token_format', 'message': 'License token must be payload.signature.'}
    payload_bytes = _b64url_decode(parts[0])
    signature = _b64url_decode(parts[1])
    public_key = serialization.load_pem_public_key(public_pem.encode('utf-8'))
    try:
        public_key.verify(signature, payload_bytes)
    except Exception:
        return {'ok': False, 'status': 'invalid_signature', 'message': 'License signature did not verify.'}
    payload = json.loads(payload_bytes.decode('utf-8'))
    expires_at = payload.get('expires_at')
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
            if expiry < datetime.now(UTC):
                return {'ok': False, 'status': 'expired', 'message': 'License expired.', 'payload': payload}
        except Exception:
            return {'ok': False, 'status': 'invalid_expiry', 'message': 'License expiry was invalid.'}
    return {'ok': True, 'status': 'verified', 'payload': payload}


def activate_license(token: str, account_email: str | None = None) -> dict[str, Any]:
    verified = verify_license_token(token)
    if not verified.get('ok'):
        record_audit_event({
            'event_type': 'license_activation_failed',
            'action_type': 'LICENSE_ACTIVATE',
            'risk_level': 'medium',
            'message': verified.get('message'),
            'payload': {'status': verified.get('status')},
        })
        return verified
    payload = verified['payload']
    license_id = payload.get('license_id') or hashlib.sha256(token.encode('utf-8')).hexdigest()[:24]
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    now = _now()
    online_activation = activate_device_online(token, payload)
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO license_records(
              license_id, account_email, tier, status, token_hash, device_fingerprint, seats,
              features_json, expires_at, activated_at, verified_at, signature_status, metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(license_id) DO UPDATE SET
              account_email=excluded.account_email,
              tier=excluded.tier,
              status=excluded.status,
              token_hash=excluded.token_hash,
              device_fingerprint=excluded.device_fingerprint,
              seats=excluded.seats,
              features_json=excluded.features_json,
              expires_at=excluded.expires_at,
              verified_at=excluded.verified_at,
              signature_status=excluded.signature_status,
              metadata_json=excluded.metadata_json
            ''',
            (
                license_id,
                account_email or payload.get('account_email'),
                payload.get('tier') or 'private_alpha',
                'active',
                token_hash,
                _device_fingerprint(),
                int(payload.get('seats') or 1),
                json.dumps(payload.get('features') or {}, sort_keys=True),
                payload.get('expires_at'),
                now,
                now,
                'ed25519_verified',
                json.dumps({'issuer': payload.get('issuer'), 'raw_payload': payload, 'online_activation': online_activation}, sort_keys=True),
            ),
        )
    record_audit_event({
        'event_type': 'license_activated',
        'action_type': 'LICENSE_ACTIVATE',
        'risk_level': 'low',
        'message': 'Activated signed Aegisure license.',
        'payload': {'license_id': license_id, 'tier': payload.get('tier'), 'account_email': account_email or payload.get('account_email')},
    })
    status = license_status()
    status['online_activation'] = online_activation
    return status


def activate_device_online(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    server = (os.getenv('AEGISURE_LICENSE_SERVER_URL') or '').rstrip('/')
    if not server:
        return {
            'ok': False,
            'status': 'license_server_not_configured',
            'message': 'Local license verified. Set AEGISURE_LICENSE_SERVER_URL to also activate/revoke devices online.',
        }
    try:
        response = httpx.post(
            f'{server}/api/devices/activate',
            json={
                'token': token,
                'device_fingerprint': _device_fingerprint(),
                'device_name': os.uname().nodename if hasattr(os, 'uname') else 'Aegisure device',
                'metadata': {
                    'platform': os.uname().sysname if hasattr(os, 'uname') else os.name,
                    'machine': os.uname().machine if hasattr(os, 'uname') else 'unknown',
                    'license_id': payload.get('license_id'),
                },
            },
            timeout=6,
        )
        data = response.json()
        return {'ok': response.is_success and bool(data.get('ok')), 'status_code': response.status_code, **data}
    except Exception as exc:
        return {
            'ok': False,
            'status': 'license_server_unreachable',
            'message': f'Local license verified, but online device activation failed: {exc}',
        }


def generate_dev_license_token(private_key_pem: str, payload: dict[str, Any]) -> str:
    private_key = serialization.load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
    body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    signature = private_key.sign(body)
    return '.'.join([
        base64.urlsafe_b64encode(body).decode('ascii').rstrip('='),
        base64.urlsafe_b64encode(signature).decode('ascii').rstrip('='),
    ])
