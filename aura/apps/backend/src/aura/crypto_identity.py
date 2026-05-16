from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import uuid
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from storage.profile_paths import profile_dir
from .privacy import redact_value, safe_json_dumps
from .state import db_conn, record_audit_event


ENC_PREFIX = 'enc:v1:'


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _secret_dir():
    path = profile_dir() / 'secrets'
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass
    return path


def _master_key_path():
    return _secret_dir() / 'aura_master.key'


def ensure_master_key() -> bytes:
    path = _master_key_path()
    if path.exists():
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return key


def _fernet() -> Fernet:
    return Fernet(ensure_master_key())


def encrypt_text(value: str) -> str:
    text = str(value or '')
    if not text or text.startswith(ENC_PREFIX):
        return text
    token = _fernet().encrypt(text.encode('utf-8')).decode('ascii')
    return f'{ENC_PREFIX}{token}'


def decrypt_text(value: str | None) -> str:
    text = str(value or '')
    if not text.startswith(ENC_PREFIX):
        return text
    token = text[len(ENC_PREFIX):].encode('ascii')
    try:
        return _fernet().decrypt(token).decode('utf-8')
    except InvalidToken:
        return '[encrypted memory unavailable: master key mismatch]'


def is_encrypted_text(value: str | None) -> bool:
    return str(value or '').startswith(ENC_PREFIX)


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _key_row(row) -> dict[str, Any]:
    data = dict(row)
    data['metadata'] = _loads(data.pop('metadata_json', None))
    data.pop('encrypted_private_key_pem', None)
    return data


def _fingerprint(public_key_pem: str) -> str:
    digest = hashes.Hash(hashes.SHA256())
    digest.update(public_key_pem.encode('utf-8'))
    return base64.urlsafe_b64encode(digest.finalize()[:18]).decode('ascii').rstrip('=')


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return safe_json_dumps(redact_value(payload)).encode('utf-8')


def ensure_identity_key(identity_id: str) -> dict[str, Any]:
    row = db_conn().execute(
        "SELECT * FROM identity_key_records WHERE identity_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (identity_id,),
    ).fetchone()
    if row:
        return _key_row(row)

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('utf-8')
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('utf-8')
    key_id = f'key_{uuid.uuid4().hex}'
    encrypted_private = encrypt_text(private_pem)
    fp = _fingerprint(public_pem)
    now = _now()
    with db_conn() as conn:
        conn.execute(
            '''
            INSERT INTO identity_key_records(
              key_id, identity_id, algorithm, public_key_pem, encrypted_private_key_pem,
              fingerprint, status, metadata_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ''',
            (
                key_id,
                identity_id,
                'ed25519',
                public_pem,
                encrypted_private,
                fp,
                'active',
                json.dumps({'local_only': True, 'hardware_bound': False, 'export_requires_approval': True}, sort_keys=True),
                now,
            ),
        )
    record_audit_event({
        'event_type': 'identity_key_created',
        'action_type': 'IDENTITY_KEY_CREATE',
        'risk_level': 'medium',
        'message': f'Created local cryptographic identity key for {identity_id}.',
        'payload': {'identity_id': identity_id, 'key_id': key_id, 'fingerprint': fp, 'algorithm': 'ed25519'},
    })
    return get_identity_key(key_id) or {'key_id': key_id, 'identity_id': identity_id, 'fingerprint': fp}


def get_identity_key(key_id: str) -> dict[str, Any] | None:
    row = db_conn().execute('SELECT * FROM identity_key_records WHERE key_id=?', (key_id,)).fetchone()
    return _key_row(row) if row else None


def list_identity_keys(identity_id: str | None = None) -> list[dict[str, Any]]:
    if identity_id:
        rows = db_conn().execute('SELECT * FROM identity_key_records WHERE identity_id=? ORDER BY created_at DESC', (identity_id,)).fetchall()
    else:
        rows = db_conn().execute('SELECT * FROM identity_key_records ORDER BY created_at DESC').fetchall()
    return [_key_row(row) for row in rows]


def _load_private_key(identity_id: str) -> ed25519.Ed25519PrivateKey:
    row = db_conn().execute(
        "SELECT * FROM identity_key_records WHERE identity_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (identity_id,),
    ).fetchone()
    if not row:
        ensure_identity_key(identity_id)
        row = db_conn().execute(
            "SELECT * FROM identity_key_records WHERE identity_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
            (identity_id,),
        ).fetchone()
    if not row:
        raise RuntimeError(f'identity key unavailable for {identity_id}')
    private_pem = decrypt_text(row['encrypted_private_key_pem']).encode('utf-8')
    return serialization.load_pem_private_key(private_pem, password=None)


def sign_identity_payload(identity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = ensure_identity_key(identity_id)
    private_key = _load_private_key(identity_id)
    message = _canonical_payload(payload)
    signature = private_key.sign(message)
    return {
        'ok': True,
        'identity_id': identity_id,
        'key_id': key['key_id'],
        'algorithm': 'ed25519',
        'fingerprint': key['fingerprint'],
        'payload_sha256': hashlib.sha256(message).hexdigest(),
        'signature': base64.urlsafe_b64encode(signature).decode('ascii').rstrip('='),
        'signed_at': _now(),
    }


def verify_identity_signature(public_key_pem: str, payload: dict[str, Any], signature: str) -> bool:
    public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
    padded = signature + '=' * (-len(signature) % 4)
    try:
        public_key.verify(base64.urlsafe_b64decode(padded), _canonical_payload(payload))
        return True
    except Exception:
        return False


def identity_attestation(identity: dict[str, Any]) -> dict[str, Any]:
    identity_id = identity.get('identity_id') or 'personal'
    key = ensure_identity_key(identity_id)
    payload = {
        'identity_id': identity_id,
        'name': identity.get('name'),
        'memory_scope': identity.get('memory_scope'),
        'policy_scope': identity.get('policy_scope'),
        'issued_at': _now(),
        'local_profile': str(profile_dir()),
    }
    signature = sign_identity_payload(identity_id, payload)
    return {
        'identity': identity,
        'key': key,
        'attestation_payload': payload,
        'signature': signature,
        'copy_resistance': {
            'private_key_encrypted_at_rest': True,
            'local_master_key_required': True,
            'hardware_binding': 'planned_for_license_server',
            'cryptographic_signing': True,
        },
    }
