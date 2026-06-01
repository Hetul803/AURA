from __future__ import annotations

from pathlib import Path

from aegisure.agent_failure_memory import AgentFailureRecord, list_agent_failures, record_agent_failure
from aegisure.constitution import scan_repository
from aegisure.diff_parser import parse_unified_diff
from aegisure.diff_risk import analyze_diff
from aegisure.policy_engine import default_policy_yaml, evaluate_policy
from aegisure.repair_prompt import generate_repair_prompt
from aegisure.second_opinion import heuristic_second_opinion


RISKY_DIFF = """diff --git a/auth/session.py b/auth/session.py
--- a/auth/session.py
+++ b/auth/session.py
@@ -1 +1,3 @@
 allowed = ["https://example.com"]
+CORS_ALLOW_ORIGIN = "*"
+password = "hunter22222"
"""


def test_policy_engine_blocks_secret_and_auth_changes():
    parsed = parse_unified_diff(RISKY_DIFF)
    report = analyze_diff(parsed)
    evaluation = evaluate_policy(parsed, policy_text=default_policy_yaml(), risk_report=report)

    assert not evaluation.passed
    decisions = {violation.decision for violation in evaluation.violations}
    assert "block" in decisions


def test_repair_prompt_is_constrained_by_constitution(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "session.py").write_text("allowed = []\n", encoding="utf-8")
    constitution = scan_repository(tmp_path)
    report = analyze_diff(RISKY_DIFF, constitution=constitution)
    repair = generate_repair_prompt(risk_report=report, constitution=constitution, failed_tests=["pytest tests/test_auth.py"], agent="claude-code")

    assert repair.agent == "claude-code"
    assert "Fix only the risks listed below" in repair.prompt
    assert "`pytest tests/test_auth.py`" in repair.prompt
    assert "secret_in_diff" in repair.prompt


def test_second_opinion_uses_static_review_without_api_keys():
    opinion = heuristic_second_opinion(RISKY_DIFF, author_agent="codex")

    assert opinion.status == "completed"
    assert opinion.agreement == "disagree"
    assert any("secret_in_diff" in concern for concern in opinion.concerns)


def test_agent_failure_memory_records_compounding_signal(tmp_path: Path):
    record_agent_failure(tmp_path, AgentFailureRecord(repo="demo", agent="codex", failure_class="test_removal", summary="Removed a regression test", repair_worked=True))

    rows = list_agent_failures(tmp_path, agent="codex")
    assert rows[0]["failure_class"] == "test_removal"
    assert rows[0]["repair_worked"] is True
