from __future__ import annotations

import pytest

from github.models import webhook_event_from_payload
from github.pr_flow import COMMENT_MARKER, process_pull_request_webhook


class FakeGitHubClient:
    def __init__(self):
        self.comments = [{"id": 10, "body": COMMENT_MARKER + "\nold"}]
        self.updated = None
        self.check_run = None

    async def create_installation_token(self, installation_id: int) -> str:
        return "installation-token"

    async def fetch_pull_request_diff(self, *, owner: str, repo: str, number: int, installation_token: str) -> str:
        return """diff --git a/auth/session.py b/auth/session.py
--- a/auth/session.py
+++ b/auth/session.py
@@ -1 +1,2 @@
 ok = True
+password = "hunter22222"
"""

    async def create_check_run(self, *, owner: str, repo: str, check_run, installation_token: str):
        self.check_run = check_run.request_payload()
        return {"id": 1, **self.check_run}

    async def list_pr_comments(self, *, owner: str, repo: str, number: int, installation_token: str):
        return self.comments

    async def update_pr_comment(self, *, owner: str, repo: str, comment_id: int, body: str, installation_token: str):
        self.updated = {"id": comment_id, "body": body}
        return self.updated

    async def post_pr_comment(self, *, owner: str, repo: str, number: int, body: str, installation_token: str):
        return {"id": 11, "body": body}


@pytest.mark.asyncio
async def test_webhook_to_check_run_and_idempotent_comment():
    event = webhook_event_from_payload(
        delivery_id="d1",
        event="pull_request",
        payload={
            "action": "opened",
            "installation": {"id": 44},
            "repository": {"id": 1, "full_name": "owner/repo", "name": "repo", "owner": {"login": "owner"}},
            "pull_request": {"id": 2, "number": 7, "title": "Risk", "state": "open", "head": {"sha": "abc"}, "base": {"sha": "def"}},
        },
    )
    fake = FakeGitHubClient()

    result = await process_pull_request_webhook(event, client=fake)

    assert result.processed is True
    assert fake.check_run["conclusion"] == "failure"
    assert fake.updated and fake.updated["id"] == 10
    assert "Aegisure PR Risk Report" in fake.updated["body"]
    assert "secret_in_diff" in fake.updated["body"]
    assert result.risk_report and result.risk_report["attribution"][0]["path"] == "auth/session.py"
