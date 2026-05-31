from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class AuthContext:
    workspace_id: str
    user_id: str


async def require_api_auth(authorization: str | None = Header(default=None), x_aura_workspace: str | None = Header(default=None)) -> AuthContext:
    token = os.getenv("AURA_API_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="AURA_API_TOKEN is required for pivot API endpoints")
    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing AURA API token")
    return AuthContext(workspace_id=x_aura_workspace or "local", user_id="api")
