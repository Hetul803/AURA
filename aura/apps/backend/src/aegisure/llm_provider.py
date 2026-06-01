from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx

from .crypto_identity import decrypt_text, encrypt_text
from .cost_router import record_model_usage
from .state import db_conn
from storage.db import init_db


ProviderName = Literal["anthropic", "openai", "ollama"]
KeyMode = Literal["provided", "byok"]


@dataclass(frozen=True)
class LLMResponse:
    provider: str
    model: str
    text: str
    status: str = "completed"
    reason: str = ""
    estimated_cost_usd: float = 0.0
    key_mode: KeyMode = "provided"

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "text": self.text,
            "status": self.status,
            "reason": self.reason,
            "estimated_cost_usd": self.estimated_cost_usd,
            "key_mode": self.key_mode,
        }


def _now_date() -> str:
    return datetime.now(UTC).date().isoformat()


def _profile_key(user_id: str, provider: str) -> str:
    return f"llm_byok:{user_id}:{provider}"


def store_user_api_key(*, user_id: str, provider: ProviderName, api_key: str) -> dict:
    init_db()
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO profile_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (_profile_key(user_id, provider), encrypt_text(api_key)),
        )
    return {"stored": True, "provider": provider, "user_id": user_id}


def get_user_api_key(*, user_id: str, provider: ProviderName) -> str | None:
    init_db()
    row = db_conn().execute("SELECT value FROM profile_meta WHERE key=?", (_profile_key(user_id, provider),)).fetchone()
    if not row:
        return None
    value = decrypt_text(row["value"])
    return value if value and not value.startswith("[encrypted") else None


def _env_key(provider: ProviderName) -> str | None:
    if provider == "anthropic":
        return os.getenv("AEGISURE_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if provider == "openai":
        return os.getenv("AEGISURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    return None


def _daily_cap_usd() -> float:
    return float(os.getenv("AEGISURE_PROVIDED_DAILY_CAP_USD", "0.25"))


def _provided_usage_today(user_id: str) -> float:
    init_db()
    rows = db_conn().execute(
        """
        SELECT estimated_cost_usd FROM model_usage_events
        WHERE json_extract(metadata_json, '$.user_id')=? AND json_extract(metadata_json, '$.key_mode')='provided'
          AND substr(created_at, 1, 10)=?
        """,
        (user_id, _now_date()),
    ).fetchall()
    return round(sum(float(row["estimated_cost_usd"] or 0) for row in rows), 6)


def cap_status(user_id: str = "default") -> dict:
    used = _provided_usage_today(user_id)
    cap = _daily_cap_usd()
    return {"user_id": user_id, "cap_usd": cap, "used_usd": used, "remaining_usd": max(0.0, round(cap - used, 6)), "reached": used >= cap}


def resolve_key(*, user_id: str, provider: ProviderName, prefer_byok: bool = True) -> tuple[str | None, KeyMode, str]:
    if prefer_byok:
        key = get_user_api_key(user_id=user_id, provider=provider)
        if key:
            return key, "byok", "using_user_supplied_key"
    status = cap_status(user_id)
    if status["reached"]:
        return None, "provided", "daily_limit_reached"
    key = _env_key(provider)
    if key:
        return key, "provided", "using_aegisure_provided_key"
    return None, "provided", "provider_key_not_configured"


class LLMProvider:
    def __init__(self, provider: ProviderName, *, model: str | None = None, user_id: str = "default", prefer_byok: bool = True):
        self.provider = provider
        self.model = model or self.default_model(provider)
        self.user_id = user_id
        self.prefer_byok = prefer_byok

    @staticmethod
    def default_model(provider: ProviderName) -> str:
        if provider == "anthropic":
            return os.getenv("AEGISURE_ANTHROPIC_REVIEW_MODEL", "claude-3-5-haiku-latest")
        if provider == "openai":
            return os.getenv("AEGISURE_OPENAI_REVIEW_MODEL", "gpt-4.1-mini")
        return os.getenv("AEGISURE_OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2"))

    async def complete(self, prompt: str) -> LLMResponse:
        if self.provider == "ollama":
            return await self._ollama(prompt)
        key, mode, reason = resolve_key(user_id=self.user_id, provider=self.provider, prefer_byok=self.prefer_byok)
        if not key:
            return LLMResponse(self.provider, self.model, "", status="unavailable", reason=reason, key_mode=mode)
        if self.provider == "anthropic":
            response = await self._anthropic(prompt, key)
        elif self.provider == "openai":
            response = await self._openai(prompt, key)
        else:
            response = LLMResponse(self.provider, self.model, "", status="unavailable", reason="unsupported_provider", key_mode=mode)
        if response.status == "completed":
            record_model_usage(
                run_id=None,
                route={"provider": response.provider, "model": response.model, "purpose": "reasoning", "route_reason": response.reason, "estimated_savings_vs_premium_usd": 0},
                prompt_tokens=max(1, len(prompt.split())),
                completion_tokens=max(1, len(response.text.split())),
                metadata={"user_id": self.user_id, "key_mode": mode, "llm_feature": True},
            )
        return LLMResponse(**{**response.to_dict(), "key_mode": mode})

    async def _anthropic(self, prompt: str, api_key: str) -> LLMResponse:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": self.model, "max_tokens": 800, "messages": [{"role": "user", "content": prompt}]},
                )
                res.raise_for_status()
                data = res.json()
                text = "\n".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
                return LLMResponse("anthropic", self.model, text, reason="anthropic_reasoning")
        except Exception as exc:
            return LLMResponse("anthropic", self.model, "", status="error", reason=str(exc))

    async def _openai(self, prompt: str, api_key: str) -> LLMResponse:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
                    json={"model": self.model, "input": prompt},
                )
                res.raise_for_status()
                data = res.json()
                text = data.get("output_text") or str(data)
                return LLMResponse("openai", self.model, text, reason="openai_reasoning")
        except Exception as exc:
            return LLMResponse("openai", self.model, "", status="error", reason=str(exc))

    async def _ollama(self, prompt: str) -> LLMResponse:
        host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                res = await client.post(f"{host}/api/generate", json={"model": self.model, "prompt": prompt, "stream": False})
                res.raise_for_status()
                return LLMResponse("ollama", self.model, res.json().get("response", ""), reason="local_ollama_reasoning", key_mode="byok")
        except Exception as exc:
            return LLMResponse("ollama", self.model, "", status="unavailable", reason=str(exc), key_mode="byok")
