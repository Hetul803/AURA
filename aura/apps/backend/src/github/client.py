from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .models import GitHubCheckRun


GITHUB_API = "https://api.github.com"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class GitHubAppConfig:
    app_id: str
    private_key_pem: str
    webhook_secret: str = ""
    api_base: str = GITHUB_API

    @classmethod
    def from_env(cls) -> "GitHubAppConfig":
        app_id = os.getenv("GITHUB_APP_ID") or os.getenv("AEGISURE_GITHUB_APP_ID") or ""
        key = os.getenv("GITHUB_APP_PRIVATE_KEY") or os.getenv("AEGISURE_GITHUB_APP_PRIVATE_KEY") or ""
        key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH") or os.getenv("AEGISURE_GITHUB_APP_PRIVATE_KEY_PATH")
        if not key and key_path:
            key = Path(key_path).read_text(encoding="utf-8")
        secret = os.getenv("GITHUB_WEBHOOK_SECRET") or os.getenv("AEGISURE_GITHUB_WEBHOOK_SECRET") or ""
        return cls(app_id=app_id, private_key_pem=key.replace("\\n", "\n"), webhook_secret=secret)

    def require_ready(self) -> None:
        if not self.app_id:
            raise RuntimeError("GITHUB_APP_ID is required")
        if not self.private_key_pem:
            raise RuntimeError("GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH is required")


def create_app_jwt(config: GitHubAppConfig, *, now: int | None = None) -> str:
    config.require_ready()
    issued_at = int(now or time.time()) - 60
    payload = {"iat": issued_at, "exp": issued_at + 600, "iss": config.app_id}
    header = {"alg": "RS256", "typ": "JWT"}
    signing_input = ".".join([
        _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
    ]).encode("ascii")
    private_key = serialization.load_pem_private_key(config.private_key_pem.encode("utf-8"), password=None)
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return signing_input.decode("ascii") + "." + _b64url(signature)


class GitHubAppClient:
    def __init__(self, config: GitHubAppConfig | None = None, *, token: str | None = None):
        self.config = config or GitHubAppConfig.from_env()
        self.token = token

    def _headers(self, token: str | None = None, *, accept: str = "application/vnd.github+json") -> dict[str, str]:
        bearer = token or self.token or create_app_jwt(self.config)
        return {
            "Accept": accept,
            "Authorization": f"Bearer {bearer}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Aegisure-Risk-Review",
        }

    async def create_installation_token(self, installation_id: int) -> str:
        async with httpx.AsyncClient(base_url=self.config.api_base, timeout=20) as client:
            response = await client.post(f"/app/installations/{installation_id}/access_tokens", headers=self._headers())
            response.raise_for_status()
            return str(response.json()["token"])

    async def fetch_pull_request_diff(self, *, owner: str, repo: str, number: int, installation_token: str) -> str:
        async with httpx.AsyncClient(base_url=self.config.api_base, timeout=30) as client:
            response = await client.get(f"/repos/{owner}/{repo}/pulls/{number}", headers=self._headers(installation_token, accept="application/vnd.github.v3.diff"))
            response.raise_for_status()
            return response.text

    async def create_check_run(self, *, owner: str, repo: str, check_run: GitHubCheckRun, installation_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.config.api_base, timeout=20) as client:
            response = await client.post(f"/repos/{owner}/{repo}/check-runs", headers=self._headers(installation_token), json=check_run.request_payload())
            response.raise_for_status()
            return response.json()

    async def post_pr_comment(self, *, owner: str, repo: str, number: int, body: str, installation_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.config.api_base, timeout=20) as client:
            response = await client.post(f"/repos/{owner}/{repo}/issues/{number}/comments", headers=self._headers(installation_token), json={"body": body})
            response.raise_for_status()
            return response.json()

    async def list_pr_comments(self, *, owner: str, repo: str, number: int, installation_token: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(base_url=self.config.api_base, timeout=20) as client:
            response = await client.get(f"/repos/{owner}/{repo}/issues/{number}/comments", headers=self._headers(installation_token))
            response.raise_for_status()
            return list(response.json())

    async def update_pr_comment(self, *, owner: str, repo: str, comment_id: int, body: str, installation_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.config.api_base, timeout=20) as client:
            response = await client.patch(f"/repos/{owner}/{repo}/issues/comments/{comment_id}", headers=self._headers(installation_token), json={"body": body})
            response.raise_for_status()
            return response.json()

    async def get_file_text(self, *, owner: str, repo: str, path: str, ref: str, installation_token: str) -> str | None:
        async with httpx.AsyncClient(base_url=self.config.api_base, timeout=20) as client:
            response = await client.get(f"/repos/{owner}/{repo}/contents/{path}", headers=self._headers(installation_token, accept="application/vnd.github.raw"), params={"ref": ref})
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.text
