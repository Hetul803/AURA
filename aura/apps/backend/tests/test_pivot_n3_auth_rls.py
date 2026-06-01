from __future__ import annotations

import base64
import hashlib
import hmac
import json

from fastapi.testclient import TestClient


def _jwt(secret: str, payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}

    def enc(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=").decode()

    signed = f"{enc(header)}.{enc(payload)}"
    sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), signed.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{signed}.{sig}"


def test_backend_locks_legacy_endpoints_without_auth(monkeypatch):
    monkeypatch.delenv("AEGISURE_LEGACY_COMPAT", raising=False)
    monkeypatch.setenv("AEGISURE_API_TOKEN", "dev-token")
    from api.main import app

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/models").status_code == 401
    assert client.get("/models", headers={"authorization": "Bearer dev-token"}).status_code == 200


def test_supabase_jwt_auth_accepted(monkeypatch):
    monkeypatch.delenv("AEGISURE_LEGACY_COMPAT", raising=False)
    monkeypatch.delenv("AEGISURE_API_TOKEN", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "supabase-secret")
    from api.main import app

    token = _jwt("supabase-secret", {"sub": "user-1", "workspace_id": "ws-1"})
    client = TestClient(app)
    res = client.post("/diffs/analyze", json={"diff": ""}, headers={"authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["workspace_id"] == "ws-1"


def test_rls_migration_contains_workspace_policies():
    text = open("alembic/versions/0001_pivot_core.py", encoding="utf-8").read()
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "current_setting('app.workspace_id'" in text
