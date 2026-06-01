from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from aegisure.agent_memory_export import EXPORT_TARGETS, build_memory_exports, write_memory_exports
from aegisure.attribution import attribution_records, infer_agent, query_attribution_ledger
from aegisure.cli import app
from aegisure.constitution import scan_repository, write_constitution
from aegisure.diff_parser import parse_unified_diff
from aegisure.provenance import build_commit_message, parse_provenance_text, read_commit_provenance


def test_cross_agent_memory_exports_are_idempotent(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Export Demo\n", encoding="utf-8")
    write_constitution(tmp_path)

    first = write_memory_exports(tmp_path)
    second = write_memory_exports(tmp_path)

    assert {item["target"] for item in first} == set(EXPORT_TARGETS)
    assert all((tmp_path / target).exists() for target in EXPORT_TARGETS)
    assert any(item["changed"] for item in first)
    assert not any(item["changed"] for item in second)


def test_export_content_targets_each_agent_style(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}', encoding="utf-8")
    constitution = scan_repository(tmp_path)
    exports = build_memory_exports(constitution)

    assert "AEGISURE_CONSTITUTION_JSON" in exports["AEGIS.md"]
    assert "Claude Code Memory" in exports["CLAUDE.md"]
    assert "GitHub Copilot Instructions" in exports[".github/copilot-instructions.md"]


def test_provenance_trailers_round_trip():
    message = build_commit_message("fix risk", agent="codex", prompt="repair only the auth test")
    parsed = parse_provenance_text(message)

    assert parsed is not None
    assert parsed.agent == "codex"
    assert parsed.prompt_excerpt == "repair only the auth test"
    assert len(parsed.prompt_hash) == 64


def test_attribution_ledger_records_agent_per_file(tmp_path: Path):
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1,2 @@
 x = 1
+y = 2
"""
    records = attribution_records(parse_unified_diff(diff), repo="demo", change_id="abc123", agent="codex")
    from aegisure.attribution import append_attribution_ledger

    append_attribution_ledger(tmp_path, records)
    rows = query_attribution_ledger(tmp_path, agent="codex")

    assert rows[0]["path"] == "a.py"
    assert rows[0]["agent"] == "codex"
    assert infer_agent(commit_message="AURA-Agent: claude-code") == "claude-code"


def test_cli_export_and_commit_capture_provenance(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Aegisure Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "feature.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.py"], cwd=tmp_path, check=True)

    runner = CliRunner()
    export_result = runner.invoke(app, ["export", "--path", str(tmp_path)])
    commit_result = runner.invoke(app, ["commit", "-m", "add feature", "--agent", "codex", "--prompt", "add a small feature", "--path", str(tmp_path)])
    provenance = read_commit_provenance(tmp_path)

    assert export_result.exit_code == 0
    assert commit_result.exit_code == 0
    assert provenance is not None
    assert provenance.agent == "codex"
    assert query_attribution_ledger(tmp_path, agent="codex")
