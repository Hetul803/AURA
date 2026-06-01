from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GitHubInstallation(BaseModel):
    installation_id: int
    account_login: str
    account_type: str = "User"


class GitHubRepository(BaseModel):
    github_id: int
    full_name: str
    owner: str
    name: str
    private: bool = False
    default_branch: str = "main"
    clone_url: str | None = None


class GitHubPullRequest(BaseModel):
    github_id: int
    number: int
    title: str
    state: str
    head_sha: str
    base_sha: str | None = None
    diff_url: str | None = None
    html_url: str | None = None


class GitHubCommit(BaseModel):
    sha: str
    message: str = ""
    author_name: str | None = None
    authored_at: datetime | None = None


class GitHubCheckRun(BaseModel):
    name: str = "Aegisure Risk Review"
    head_sha: str
    status: Literal["queued", "in_progress", "completed"] = "completed"
    conclusion: Literal["success", "neutral", "failure", "cancelled", "skipped", "timed_out", "action_required"] | None = None
    title: str
    summary: str
    text: str = ""

    def request_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "head_sha": self.head_sha,
            "status": self.status,
            "conclusion": self.conclusion,
            "output": {"title": self.title, "summary": self.summary, "text": self.text},
        }


class GitHubWebhookEvent(BaseModel):
    delivery_id: str
    event: str
    action: str | None = None
    installation_id: int | None = None
    repository: GitHubRepository | None = None
    pull_request: GitHubPullRequest | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


def repository_from_payload(payload: dict[str, Any]) -> GitHubRepository | None:
    repo = payload.get("repository") or {}
    if not repo:
        return None
    owner = (repo.get("owner") or {}).get("login") or repo.get("full_name", "/").split("/")[0]
    return GitHubRepository(
        github_id=int(repo.get("id") or 0),
        full_name=repo.get("full_name") or f"{owner}/{repo.get('name', '')}",
        owner=owner,
        name=repo.get("name") or "",
        private=bool(repo.get("private")),
        default_branch=repo.get("default_branch") or "main",
        clone_url=repo.get("clone_url"),
    )


def pull_request_from_payload(payload: dict[str, Any]) -> GitHubPullRequest | None:
    pr = payload.get("pull_request") or {}
    if not pr:
        return None
    return GitHubPullRequest(
        github_id=int(pr.get("id") or 0),
        number=int(pr.get("number") or payload.get("number") or 0),
        title=pr.get("title") or "",
        state=pr.get("state") or "",
        head_sha=((pr.get("head") or {}).get("sha") or ""),
        base_sha=((pr.get("base") or {}).get("sha") or None),
        diff_url=pr.get("diff_url"),
        html_url=pr.get("html_url"),
    )


def webhook_event_from_payload(*, delivery_id: str, event: str, payload: dict[str, Any]) -> GitHubWebhookEvent:
    installation = payload.get("installation") or {}
    return GitHubWebhookEvent(
        delivery_id=delivery_id,
        event=event,
        action=payload.get("action"),
        installation_id=installation.get("id"),
        repository=repository_from_payload(payload),
        pull_request=pull_request_from_payload(payload),
        raw=payload,
    )
