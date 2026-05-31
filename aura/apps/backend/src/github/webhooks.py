from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

from storage.db import init_db
from aura.state import db_conn

from .models import GitHubWebhookEvent, webhook_event_from_payload


class WebhookVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class WebhookHeaders:
    event: str
    delivery_id: str
    signature_256: str


def verify_signature(raw_body: bytes, signature_256: str, secret: str) -> bool:
    if not secret:
        raise WebhookVerificationError("GITHUB_WEBHOOK_SECRET is required")
    if not signature_256.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_256)


def _profile_key(delivery_id: str) -> str:
    return f"github_webhook_delivery:{delivery_id}"


def delivery_seen(delivery_id: str) -> bool:
    init_db()
    row = db_conn().execute("SELECT value FROM profile_meta WHERE key=?", (_profile_key(delivery_id),)).fetchone()
    return bool(row)


def mark_delivery_seen(delivery_id: str, event: str) -> None:
    init_db()
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO profile_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING",
            (_profile_key(delivery_id), event),
        )


def parse_verified_webhook(raw_body: bytes, headers: WebhookHeaders, *, secret: str) -> tuple[GitHubWebhookEvent, bool]:
    if not verify_signature(raw_body, headers.signature_256, secret):
        raise WebhookVerificationError("Invalid GitHub webhook signature")
    duplicate = delivery_seen(headers.delivery_id)
    payload = json.loads(raw_body.decode("utf-8"))
    event = webhook_event_from_payload(delivery_id=headers.delivery_id, event=headers.event, payload=payload)
    if not duplicate:
        mark_delivery_seen(headers.delivery_id, headers.event)
    return event, duplicate
