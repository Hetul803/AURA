"""pivot core tables

Revision ID: 0001_pivot_core
Revises:
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_pivot_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "workspaces",
        sa.Column("workspace_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("display_name", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
    )
    op.create_table(
        "github_installations",
        sa.Column("workspace_id", sa.String(), nullable=False, index=True),
        sa.Column("installation_id", sa.BigInteger(), primary_key=True),
        sa.Column("account_login", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "github_repositories",
        sa.Column("repository_id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), nullable=False, index=True),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("default_branch", sa.String(), nullable=False, server_default="main"),
        sa.Column("private", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "github_pull_requests",
        sa.Column("pull_request_id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), nullable=False, index=True),
        sa.Column("repository_id", sa.String(), nullable=False, index=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("head_sha", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
    )
    for table in [
        "diff_analyses",
        "risk_findings",
        "constitutions",
        "constitution_versions",
        "agent_memory_exports",
        "repair_prompts",
        "second_opinions",
        "provenance_records",
        "attribution_ledger",
        "policy_rules",
        "policy_evaluations",
        "agent_failure_records",
        "waitlist_signups",
        "founding_pledges",
    ]:
        op.create_table(
            table,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("workspace_id", sa.String(), nullable=False, index=True),
            sa.Column("repository_id", sa.String(), index=True),
            sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )


def downgrade() -> None:
    for table in [
        "founding_pledges",
        "waitlist_signups",
        "agent_failure_records",
        "policy_evaluations",
        "policy_rules",
        "attribution_ledger",
        "provenance_records",
        "second_opinions",
        "repair_prompts",
        "agent_memory_exports",
        "constitution_versions",
        "constitutions",
        "risk_findings",
        "diff_analyses",
        "github_pull_requests",
        "github_repositories",
        "github_installations",
        "workspace_members",
        "users",
        "workspaces",
    ]:
        op.drop_table(table)
