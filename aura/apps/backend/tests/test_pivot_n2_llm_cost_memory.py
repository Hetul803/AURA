from __future__ import annotations

from pathlib import Path

import pytest

from aegisure.diff_risk import analyze_diff
from aegisure.llm_provider import LLMProvider, cap_status, get_user_api_key, resolve_key, store_user_api_key
from aegisure.memory_timeline import MemoryTimelineEvent, append_local_memory_event, list_local_memory_timeline


def test_free_static_core_runs_without_llm_keys(monkeypatch):
    for key in ["AEGISURE_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", "AEGISURE_OPENAI_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    report = analyze_diff("""diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 print("ok")
+password = "hunter22222"
""")
    assert report.verdict == "block"
    assert any(f.category == "secret_in_diff" for f in report.findings)


def test_byok_keys_are_encrypted_and_resolved(monkeypatch, tmp_path):
    monkeypatch.setenv("PROFILE_DIR_OVERRIDE", str(tmp_path))
    store_user_api_key(user_id="u1", provider="anthropic", api_key="sk-ant-test")

    assert get_user_api_key(user_id="u1", provider="anthropic") == "sk-ant-test"
    key, mode, reason = resolve_key(user_id="u1", provider="anthropic")
    assert key == "sk-ant-test"
    assert mode == "byok"
    assert reason == "using_user_supplied_key"


@pytest.mark.asyncio
async def test_provider_gracefully_reports_missing_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("PROFILE_DIR_OVERRIDE", str(tmp_path))
    monkeypatch.delenv("AEGISURE_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = await LLMProvider("anthropic", user_id="u2", prefer_byok=False).complete("explain diff")

    assert response.status == "unavailable"
    assert response.reason in {"provider_key_not_configured", "daily_limit_reached"}
    assert cap_status("u2")["cap_usd"] >= 0


def test_memory_timeline_is_workspace_and_agent_scoped(tmp_path: Path):
    append_local_memory_event(tmp_path, MemoryTimelineEvent(workspace_id="ws1", repo_id="repo1", agent="codex", event_type="diff_analyzed", summary="Codex touched auth", payload={"path": "auth.py"}))
    append_local_memory_event(tmp_path, MemoryTimelineEvent(workspace_id="ws2", repo_id="repo1", agent="claude-code", event_type="reviewed", summary="Claude reviewed", payload={}))

    assert len(list_local_memory_timeline(tmp_path, workspace_id="ws1")) == 1
    assert list_local_memory_timeline(tmp_path, agent="codex")[0]["summary"] == "Codex touched auth"
