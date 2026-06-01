from __future__ import annotations

import os
import base64
import hashlib
import hmac
import json
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class AuthContext:
    workspace_id: str
    user_id: str


async def require_api_auth(
    authorization: str | None = Header(default=None),
    x_aura_workspace: str | None = Header(default=None),
    x_aegisure_workspace: str | None = Header(default=None),
) -> AuthContext:
    return auth_context_from_header(authorization, x_aegisure_workspace or x_aura_workspace)


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def verify_supabase_jwt(token: str) -> dict:
    secret = os.getenv("SUPABASE_JWT_SECRET") or os.getenv("AEGISURE_SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="SUPABASE_JWT_SECRET is required")
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signed = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature_b64)):
            raise HTTPException(status_code=401, detail="Invalid Supabase JWT signature")
        return json.loads(_b64decode(payload_b64))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Supabase JWT") from exc


def auth_context_from_header(authorization: str | None, workspace: str | None = None) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    api_token = os.getenv("AEGISURE_API_TOKEN") or os.getenv("AURA_API_TOKEN")
    if api_token and hmac.compare_digest(token, api_token):
        return AuthContext(workspace_id=workspace or "local", user_id="api")
    payload = verify_supabase_jwt(token)
    return AuthContext(workspace_id=workspace or payload.get("workspace_id") or "default", user_id=payload.get("sub") or payload.get("email") or "supabase")
