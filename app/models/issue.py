import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.columns import str_enum
from app.models.enums import IssueChangeKind, IssueFactType, IssueMemberRole, IssueStatus


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        Index("ix_issues_org_status_activity", "organization_id", "status", "last_activity_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    edition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("editions.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[IssueStatus] = mapped_column(
        str_enum(IssueStatus, "issue_status"), default=IssueStatus.active
    )
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id"), nullable=True
    )
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    last_change_kind: Mapped[IssueChangeKind | None] = mapped_column(
        str_enum(IssueChangeKind, "issue_change_kind"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IssueMember(Base):
    __tablename__ = "issue_members"
    __table_args__ = (UniqueConstraint("issue_id", "post_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id"), nullable=False, index=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), nullable=False, index=True
    )
    role: Mapped[IssueMemberRole] = mapped_column(
        str_enum(IssueMemberRole, "issue_member_role"), default=IssueMemberRole.origin
    )
    similarity: Mapped[float] = mapped_column(Float, default=1.0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IssueRevision(Base):
    __tablename__ = "issue_revisions"
    __table_args__ = (Index("ix_issue_revisions_issue_occurred", "issue_id", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id"), nullable=False, index=True
    )
    kind: Mapped[IssueChangeKind] = mapped_column(
        str_enum(IssueChangeKind, "issue_change_kind"), nullable=False
    )
    fact_type: Mapped[IssueFactType | None] = mapped_column(
        str_enum(IssueFactType, "issue_fact_type"), nullable=True
    )
    headline: Mapped[str] = mapped_column(String(512), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="")
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), nullable=True
    )
    duplicate_post_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserIssueSeen(Base):
    __tablename__ = "user_issue_seen"
    __table_args__ = (UniqueConstraint("user_id", "issue_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id"), nullable=False, index=True
    )
    tracking: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
