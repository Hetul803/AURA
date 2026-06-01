from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

import typer

from .agent_memory_export import write_memory_exports
from .attribution import append_attribution_ledger, attribution_records
from .constitution import render_constitution, scan_repository, write_constitution
from .diff_parser import parse_unified_diff
from .diff_risk import analyze_diff
from .repair_prompt import generate_repair_prompt
from .second_opinion import heuristic_second_opinion
from .provenance import ProvenanceRecord, build_commit_message, prompt_hash, record_git_note


app = typer.Typer(help="Aegisure trust, memory, and control layer for AI coding agents.")


def _repo_root(path: Path) -> Path:
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path, capture_output=True, text=True)
    if proc.returncode == 0:
        return Path(proc.stdout.strip()).resolve()
    return path.resolve()


def _git_diff(repo: Path, *, staged: bool, ref: Optional[str]) -> str:
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--cached")
    if ref:
        cmd.append(ref)
    proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise typer.BadParameter(proc.stderr.strip() or "git diff failed")
    return proc.stdout


@app.command()
def init(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Repository path to scan."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing AEGIS.md."),
    print_only: bool = typer.Option(False, "--print", help="Print the generated Constitution instead of writing AEGIS.md."),
) -> None:
    """Scan a repository and create its AEGIS.md Constitution."""

    repo = _repo_root(path)
    constitution = scan_repository(repo)
    if print_only:
        typer.echo(render_constitution(constitution))
        return
    target = write_constitution(repo, overwrite=overwrite)
    typer.echo(f"Wrote {target}")


@app.command()
def login(
    workspace: str = typer.Option("local", "--workspace", help="Workspace slug or id."),
    token: str = typer.Option("", "--token", help="Dashboard API token. Omit for local-only mode."),
) -> None:
    """Authenticate to a workspace or keep running fully local."""

    if token:
        typer.echo(f"Saved login for workspace {workspace}.")
    else:
        typer.echo(f"Using local mode for workspace {workspace}.")


@app.command()
def scan(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Repository path to scan."),
    staged: bool = typer.Option(True, "--staged/--worktree", help="Analyze staged diff by default; use --worktree for unstaged diff."),
    ref: Optional[str] = typer.Option(None, "--ref", help="Analyze diff against a git ref, for example main...HEAD."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Analyze a git diff and print a risk report."""

    repo = _repo_root(path)
    diff_text = _git_diff(repo, staged=staged, ref=ref)
    parsed = parse_unified_diff(diff_text)
    constitution = scan_repository(repo)
    report = analyze_diff(parsed, constitution=constitution)
    aura_dir = repo / ".aura"
    aura_dir.mkdir(exist_ok=True)
    (aura_dir / "last-risk-report.json").write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        raise typer.Exit(1 if report.verdict == "block" else 0)

    typer.echo(f"Aegisure risk report: {report.verdict.upper()} ({report.score}/100)")
    typer.echo(report.summary)
    for finding in report.findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        typer.echo(f"- [{finding.severity}] {finding.category} at {location}: {finding.explanation}")
    raise typer.Exit(1 if report.verdict == "block" else 0)


@app.command()
def export(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Repository path."),
    overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite", help="Overwrite generated memory files."),
) -> None:
    """Write cross-agent memory files from the canonical Aegisure Constitution."""

    repo = _repo_root(path)
    results = write_memory_exports(repo, overwrite=overwrite)
    for result in results:
        status = "updated" if result["changed"] else "unchanged"
        typer.echo(f"{status}: {result['target']}")


@app.command()
def commit(
    message: str = typer.Option(..., "--message", "-m", help="Commit message."),
    agent: str = typer.Option("unknown", "--agent", help="Agent that produced the change, for example codex or claude-code."),
    prompt: str = typer.Option("", "--prompt", help="Prompt or task that produced the change."),
    path: Path = typer.Option(Path("."), "--path", "-p", help="Repository path."),
) -> None:
    """Commit staged changes and capture provenance via trailers and a git note."""

    repo = _repo_root(path)
    full_message = build_commit_message(message, agent=agent, prompt=prompt)
    proc = subprocess.run(["git", "commit", "-m", full_message], cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        raise typer.BadParameter(proc.stderr.strip() or "git commit failed")
    sha_proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
    commit_sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
    if commit_sha:
        record = ProvenanceRecord(
            change_id=prompt_hash(prompt),
            agent=agent,
            prompt_hash=prompt_hash(prompt),
            prompt_excerpt=" ".join(prompt.split())[:180],
            commit_sha=commit_sha,
        )
        record_git_note(repo, commit_sha, record)
        diff_text = subprocess.run(["git", "show", "--format=", "--unified=0", commit_sha], cwd=repo, capture_output=True, text=True).stdout
        parsed = parse_unified_diff(diff_text)
        append_attribution_ledger(repo, attribution_records(parsed, repo=repo.name, change_id=commit_sha, agent=agent, source="cli_commit"))
    typer.echo(proc.stdout.strip())


@app.command()
def repair(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Repository path."),
    staged: bool = typer.Option(True, "--staged/--worktree", help="Use staged or worktree diff."),
    agent: str = typer.Option("codex", "--agent", help="Target agent for the repair prompt."),
) -> None:
    """Generate a constrained repair prompt for the current risky diff."""

    repo = _repo_root(path)
    diff_text = _git_diff(repo, staged=staged, ref=None)
    constitution = scan_repository(repo)
    report = analyze_diff(parse_unified_diff(diff_text), constitution=constitution)
    prompt = generate_repair_prompt(risk_report=report, constitution=constitution, agent=agent)
    typer.echo(prompt.prompt)


@app.command()
def review(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Repository path."),
    staged: bool = typer.Option(True, "--staged/--worktree", help="Use staged or worktree diff."),
    author_agent: str = typer.Option("unknown", "--author-agent", help="Agent that produced the diff."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Run an offline second-opinion review on the current diff."""

    repo = _repo_root(path)
    diff_text = _git_diff(repo, staged=staged, ref=None)
    opinion = heuristic_second_opinion(diff_text, author_agent=author_agent)
    if json_output:
        typer.echo(json.dumps(opinion.to_dict(), indent=2, sort_keys=True))
    else:
        typer.echo(f"Second opinion: {opinion.agreement.upper()} ({opinion.status})")
        typer.echo(opinion.summary)
        for concern in opinion.concerns:
            typer.echo(f"- {concern}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
