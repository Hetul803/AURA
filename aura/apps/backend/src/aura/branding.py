from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .state import db_conn


DEFAULT_BRAND = {
    'product_name': 'AURA',
    'assistant_default_name': 'AURA',
    'company_name': 'AURA Labs',
    'tagline': 'Private AI operating identity',
    'support_url': '',
    'download_url': '',
    'license_public_key_configured': False,
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _repo_brand_file() -> Path:
    return Path(__file__).resolve().parents[4] / 'config' / 'brand.json'


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _file_brand() -> dict[str, Any]:
    path = _repo_brand_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def get_brand() -> dict[str, Any]:
    row = db_conn().execute("SELECT value_json FROM brand_settings WHERE key='brand'").fetchone()
    stored = _loads(row['value_json']) if row else {}
    env = {
        key: value for key, value in {
            'product_name': os.getenv('AURA_PRODUCT_NAME'),
            'assistant_default_name': os.getenv('AURA_ASSISTANT_NAME'),
            'company_name': os.getenv('AURA_COMPANY_NAME'),
            'support_url': os.getenv('AURA_SUPPORT_URL'),
            'download_url': os.getenv('AURA_DOWNLOAD_URL'),
        }.items() if value
    }
    brand = {**DEFAULT_BRAND, **_file_brand(), **stored, **env}
    brand['license_public_key_configured'] = bool(os.getenv('AURA_LICENSE_PUBLIC_KEY') or os.getenv('AURA_VENDOR_PUBLIC_KEY'))
    return brand


def update_brand(patch: dict[str, Any]) -> dict[str, Any]:
    allowed = set(DEFAULT_BRAND) | {'privacy_url', 'terms_url', 'app_id', 'artifact_name'}
    current = get_brand()
    next_brand = {**current, **{key: value for key, value in patch.items() if key in allowed and value is not None}}
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO brand_settings(key,value_json,updated_at) VALUES('brand',?,?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
            """,
            (json.dumps(next_brand, sort_keys=True), _now()),
        )
    return get_brand()
