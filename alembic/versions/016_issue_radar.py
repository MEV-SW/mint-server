"""Issue radar: issues, issue_members, issue_revisions, user_issue_seen.

Revision ID: 016
Revises: 015
Create Date: 2026-09-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("edition_id", UUID, sa.ForeignKey("editions.id"), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("merged_into_id", UUID, sa.ForeignKey("issues.id"), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_change_kind", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_issues_organization_id", "issues", ["organization_id"])
    op.create_index("ix_issues_edition_id", "issues", ["edition_id"])
    op.create_index("ix_issues_last_activity_at", "issues", ["last_activity_at"])
    op.create_index(
        "ix_issues_org_status_activity", "issues", ["organization_id", "status", "last_activity_at"]
    )

    op.create_table(
        "issue_members",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("issue_id", UUID, sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("post_id", UUID, sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="origin"),
        sa.Column("similarity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("issue_id", "post_id"),
    )
    op.create_index("ix_issue_members_issue_id", "issue_members", ["issue_id"])
    op.create_index("ix_issue_members_post_id", "issue_members", ["post_id"])

    op.create_table(
        "issue_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("issue_id", UUID, sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("fact_type", sa.String(16), nullable=True),
        sa.Column("headline", sa.String(512), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("post_id", UUID, sa.ForeignKey("posts.id"), nullable=True),
        sa.Column("duplicate_post_ids", postgresql.JSON(), nullable=True),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("prompt_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_issue_revisions_issue_id", "issue_revisions", ["issue_id"])
    op.create_index("ix_issue_revisions_occurred_at", "issue_revisions", ["occurred_at"])
    op.create_index(
        "ix_issue_revisions_issue_occurred", "issue_revisions", ["issue_id", "occurred_at"]
    )

    op.create_table(
        "user_issue_seen",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issue_id", UUID, sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("tracking", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "issue_id"),
    )
    op.create_index("ix_user_issue_seen_user_id", "user_issue_seen", ["user_id"])
    op.create_index("ix_user_issue_seen_issue_id", "user_issue_seen", ["issue_id"])


def downgrade() -> None:
    for table in ("user_issue_seen", "issue_revisions", "issue_members", "issues"):
        op.drop_table(table)
