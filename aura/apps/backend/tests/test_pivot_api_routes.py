from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from api.main import app


def test_pivot_api_requires_auth(monkeypatch):
    monkeypatch.setenv("AURA_API_TOKEN", "dev-token")
    client = TestClient(app)

    res = client.post("/diffs/analyze", json={"diff": ""})
    assert res.status_code == 401


def test_pivot_diff_analyze_authenticated(monkeypatch):
    monkeypatch.setenv("AURA_API_TOKEN", "dev-token")
    client = TestClient(app)
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 print("ok")
+password = "hunter22222"
"""
    res = client.post("/diffs/analyze", json={"diff": diff}, headers={"authorization": "Bearer dev-token", "x-aura-workspace": "ws_1"})
    body = res.json()

    assert res.status_code == 200
    assert body["workspace_id"] == "ws_1"
    assert body["verdict"] == "block"


def test_github_webhook_route_is_hmac_verified(monkeypatch, tmp_path):
    monkeypatch.setenv("PROFILE_DIR_OVERRIDE", str(tmp_path))
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    client = TestClient(app)
    payload = {"action": "opened", "installation": {"id": 1}, "repository": {"id": 2, "full_name": "o/r", "name": "r", "owner": {"login": "o"}}}
    raw = json.dumps(payload).encode("utf-8")
    sig = "sha256=" + hmac.new(b"secret", raw, hashlib.sha256).hexdigest()

    res = client.post(
        "/github/webhook",
        content=raw,
        headers={
            "x-github-event": "pull_request",
            "x-github-delivery": "delivery-api-1",
            "x-hub-signature-256": sig,
            "content-type": "application/json",
        },
    )

    assert res.status_code == 200
    assert res.json()["ok"] is True
