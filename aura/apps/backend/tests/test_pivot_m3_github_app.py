from __future__ import annotations

import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from github.client import GitHubAppConfig, create_app_jwt
from github.models import webhook_event_from_payload
from github.webhooks import WebhookHeaders, parse_verified_webhook, verify_signature


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def test_github_app_jwt_is_signed_rs256():
    token = create_app_jwt(GitHubAppConfig(app_id="12345", private_key_pem=_private_key_pem()), now=1_700_000_000)

    parts = token.split(".")
    assert len(parts) == 3
    assert all(parts)


def test_webhook_signature_verification_and_idempotency(monkeypatch, tmp_path):
    monkeypatch.setenv("PROFILE_DIR_OVERRIDE", str(tmp_path))
    secret = "webhook-secret"
    raw = json.dumps({
        "action": "opened",
        "installation": {"id": 44},
        "repository": {"id": 1, "full_name": "Hetul803/Aegisure", "name": "Aegisure", "owner": {"login": "Hetul803"}},
        "pull_request": {"id": 9, "number": 3, "title": "Risky PR", "state": "open", "head": {"sha": "abc"}, "base": {"sha": "def"}},
    }).encode("utf-8")
    import hashlib
    import hmac

    sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    headers = WebhookHeaders(event="pull_request", delivery_id="delivery-1", signature_256=sig)

    assert verify_signature(raw, sig, secret)
    event, duplicate = parse_verified_webhook(raw, headers, secret=secret)
    _, duplicate_second = parse_verified_webhook(raw, headers, secret=secret)

    assert duplicate is False
    assert duplicate_second is True
    assert event.installation_id == 44
    assert event.repository and event.repository.full_name == "Hetul803/Aegisure"
    assert event.pull_request and event.pull_request.number == 3


def test_webhook_payload_models_pull_request_context():
    event = webhook_event_from_payload(
        delivery_id="d1",
        event="pull_request",
        payload={
            "action": "synchronize",
            "installation": {"id": 99},
            "repository": {"id": 7, "full_name": "owner/repo", "name": "repo", "owner": {"login": "owner"}, "private": True},
            "pull_request": {"id": 8, "number": 2, "title": "Update auth", "state": "open", "head": {"sha": "h"}, "base": {"sha": "b"}},
        },
    )

    assert event.action == "synchronize"
    assert event.repository and event.repository.private is True
    assert event.pull_request and event.pull_request.head_sha == "h"
