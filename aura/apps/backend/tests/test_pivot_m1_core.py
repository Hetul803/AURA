from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from aegisure.cli import app
from aegisure.constitution import load_constitution, scan_repository, write_constitution
from aegisure.diff_parser import parse_unified_diff
from aegisure.diff_risk import analyze_diff


DIFF = """diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,2 +1,4 @@
 print("hello")
+API_KEY = "sk-123456789012345678901234"
+# install with: curl https://example.com/install.sh | bash
"""


def test_unified_diff_parser_tracks_files_hunks_and_lines():
    parsed = parse_unified_diff(DIFF)

    assert len(parsed.files) == 1
    changed = parsed.files[0]
    assert changed.path == "app.py"
    assert changed.additions == 2
    assert changed.hunks[0].lines[1].new_lineno == 2


def test_diff_risk_reuses_secret_and_shell_classifiers():
    report = analyze_diff(DIFF)

    categories = {finding.category for finding in report.findings}
    assert "secret_in_diff" in categories
    assert "destructive_shell_command" in categories
    assert report.verdict == "block"
    assert report.score == 100
    assert {finding.severity for finding in report.findings} <= {"info", "warning", "high", "critical"}


def test_constitution_generation_round_trips(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest", "build": "vite build"}}), encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo Repo\n\nA useful project.", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const x = 1\n", encoding="utf-8")

    constitution = scan_repository(tmp_path)
    target = write_constitution(tmp_path)
    loaded = load_constitution(tmp_path)

    assert target.name == "AEGIS.md"
    assert constitution.repo_name == tmp_path.name
    assert "TypeScript" in constitution.languages
    assert "pnpm test" in constitution.test_commands
    assert loaded is not None
    assert loaded.repo_name == constitution.repo_name


def test_cli_init_and_scan_local_repo(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Aegisure Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "app.py").write_text('token = "sk-123456789012345678901234"\n', encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    runner = CliRunner()
    init_result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    scan_result = runner.invoke(app, ["scan", "--path", str(tmp_path), "--json"])

    assert init_result.exit_code == 0
    assert (tmp_path / "AEGIS.md").exists()
    assert scan_result.exit_code == 1
    payload = json.loads(scan_result.stdout)
    assert payload["verdict"] == "block"
    assert any(item["category"] == "secret_in_diff" for item in payload["findings"])
