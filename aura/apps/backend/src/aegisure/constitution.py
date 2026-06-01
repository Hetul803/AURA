from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CONSTITUTION_FILENAME = "AEGIS.md"
_JSON_START = "<!-- AEGISURE_CONSTITUTION_JSON"
_JSON_END = "AEGISURE_CONSTITUTION_JSON -->"


@dataclass(frozen=True)
class Constitution:
    repo_name: str
    summary: str
    languages: list[str]
    package_files: list[str]
    test_commands: list[str]
    protected_paths: list[str]
    agent_rules: list[str]
    approval_rules: list[str]
    memory_exports: list[str] = field(default_factory=list)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repo_name": self.repo_name,
            "summary": self.summary,
            "languages": self.languages,
            "package_files": self.package_files,
            "test_commands": self.test_commands,
            "protected_paths": self.protected_paths,
            "agent_rules": self.agent_rules,
            "approval_rules": self.approval_rules,
            "memory_exports": self.memory_exports,
        }


def _read_text(path: Path, limit: int = 12000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return ""


def _json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _language_from_suffix(path: Path) -> str | None:
    mapping = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
        ".php": "PHP",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".cs": "C#",
    }
    return mapping.get(path.suffix.lower())


def _discover_languages(repo_path: Path) -> list[str]:
    counts: dict[str, int] = {}
    ignored = {".git", "node_modules", "dist", "build", ".next", "venv", ".venv", "__pycache__"}
    for path in repo_path.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        lang = _language_from_suffix(path)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]]


def _package_files(repo_path: Path) -> list[str]:
    names = [
        "package.json",
        "pnpm-workspace.yaml",
        "pyproject.toml",
        "requirements.txt",
        "go.mod",
        "Cargo.toml",
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "Dockerfile",
        "docker-compose.yml",
    ]
    return sorted(str(path.relative_to(repo_path)) for name in names for path in repo_path.rglob(name) if ".git" not in path.parts and "node_modules" not in path.parts)


def _test_commands(repo_path: Path) -> list[str]:
    commands: list[str] = []
    package = _json_file(repo_path / "package.json")
    scripts = package.get("scripts") or {}
    for key in ["test", "lint", "typecheck", "build"]:
        if key in scripts:
            commands.append(f"pnpm {key}")
    for package_path in repo_path.rglob("package.json"):
        if package_path == repo_path / "package.json" or "node_modules" in package_path.parts:
            continue
        data = _json_file(package_path)
        rel = package_path.parent.relative_to(repo_path)
        scripts = data.get("scripts") or {}
        for key in ["test", "lint", "typecheck", "build"]:
            if key in scripts:
                commands.append(f"pnpm --dir {rel} {key}")
    if (repo_path / "pyproject.toml").exists() or (repo_path / "pytest.ini").exists():
        commands.append("pytest")
    for pyproject in repo_path.rglob("pyproject.toml"):
        if pyproject != repo_path / "pyproject.toml" and ".venv" not in pyproject.parts:
            commands.append(f"cd {pyproject.parent.relative_to(repo_path)} && pytest")
    return sorted(dict.fromkeys(commands))


def _protected_paths(repo_path: Path) -> list[str]:
    candidates = [
        ".env",
        ".env.local",
        ".github/workflows/",
        "infra/",
        "migrations/",
        "alembic/",
        "schema.sql",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
    ]
    protected = [item for item in candidates if (repo_path / item.rstrip("/")).exists()]
    for path in repo_path.rglob("*"):
        rel = str(path.relative_to(repo_path))
        if re.search(r"(?i)(payment|billing|stripe|auth|login|oauth|permission|policy|migration)", rel):
            if path.is_dir():
                rel += "/"
            protected.append(rel)
    return sorted(dict.fromkeys(protected))[:60]


def _summary(repo_path: Path) -> str:
    readme = _read_text(repo_path / "README.md", limit=4000)
    for line in readme.splitlines():
        stripped = line.strip(" #\t")
        if stripped and not stripped.lower().startswith(("badge", "img", "http")):
            return stripped[:240]
    return f"{repo_path.name} repository"


def scan_repository(repo_path: str | Path) -> Constitution:
    path = Path(repo_path).resolve()
    protected = _protected_paths(path)
    return Constitution(
        repo_name=path.name,
        summary=_summary(path),
        languages=_discover_languages(path),
        package_files=_package_files(path),
        test_commands=_test_commands(path),
        protected_paths=protected,
        agent_rules=[
            "Inspect before editing; explain the smallest safe change.",
            "Do not remove tests or safety checks to make a task pass.",
            "Do not touch secrets, credentials, or private keys.",
            "Keep changes scoped to the requested task.",
            "Add or update regression tests for behavior changes.",
            "Ask for human approval before protected paths or high-risk actions.",
        ],
        approval_rules=[
            "Payments, billing, auth, permissions, deploy config, and database migrations require human review.",
            "Deleting tests, weakening CORS, adding risky dependencies, or changing CI requires human review.",
            "Shell commands that are destructive or pipe remote scripts into a shell are blocked.",
        ],
        memory_exports=["AEGIS.md", "AGENTS.md", "CLAUDE.md", ".cursorrules", ".clinerules", ".github/copilot-instructions.md"],
    )


def render_constitution(constitution: Constitution) -> str:
    data = constitution.to_dict()
    lines = [
        f"# Aegisure Constitution for {constitution.repo_name}",
        "",
        constitution.summary,
        "",
        "## Purpose",
        "This file is the project Constitution for AI coding agents. It tells Codex, Claude Code, Cursor, Copilot, Cline, Roo, and humans what must be preserved.",
        "",
        "## Detected Stack",
        *(f"- {lang}" for lang in constitution.languages or ["Unknown"]),
        "",
        "## Package And Build Files",
        *(f"- `{path}`" for path in constitution.package_files or ["No package files detected"]),
        "",
        "## Test Commands",
        *(f"- `{command}`" for command in constitution.test_commands or ["Add a test command before relying on autonomous agents"]),
        "",
        "## Protected Paths",
        *(f"- `{path}`" for path in constitution.protected_paths or ["No protected paths detected yet"]),
        "",
        "## Agent Rules",
        *(f"- {rule}" for rule in constitution.agent_rules),
        "",
        "## Approval Rules",
        *(f"- {rule}" for rule in constitution.approval_rules),
        "",
        "## Cross-Agent Memory Exports",
        *(f"- `{target}`" for target in constitution.memory_exports),
        "",
        _JSON_START,
        json.dumps(data, indent=2, sort_keys=True),
        _JSON_END,
        "",
    ]
    return "\n".join(lines)


def write_constitution(repo_path: str | Path, *, overwrite: bool = False) -> Path:
    path = Path(repo_path).resolve() / CONSTITUTION_FILENAME
    if path.exists() and not overwrite:
        return path
    path.write_text(render_constitution(scan_repository(repo_path)), encoding="utf-8")
    return path


def load_constitution(repo_path: str | Path) -> Constitution | None:
    path = Path(repo_path).resolve() / CONSTITUTION_FILENAME
    text = _read_text(path)
    if not text or _JSON_START not in text or _JSON_END not in text:
        return None
    try:
        payload = text.split(_JSON_START, 1)[1].split(_JSON_END, 1)[0].strip()
        data = json.loads(payload)
        return Constitution(**data)
    except Exception:
        return None


def constitution_for_repo(repo_path: str | Path) -> Constitution:
    return load_constitution(repo_path) or scan_repository(repo_path)


def check_constitution_violations(changed_paths: list[str], constitution: Constitution) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    protected = [item.rstrip("/") for item in constitution.protected_paths]
    for changed in changed_paths:
        normalized = changed.strip("/")
        for protected_path in protected:
            if normalized == protected_path or normalized.startswith(protected_path.rstrip("/") + "/"):
                findings.append({
                    "category": "constitution_violation",
                    "severity": "high",
                    "path": changed,
                    "explanation": f"`{changed}` is protected by AEGIS.md and needs human review.",
                })
                break
    return findings
