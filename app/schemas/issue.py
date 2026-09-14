from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import BoardType, IssueChangeKind, IssueFactType, IssueStatus


class IssueListItem(BaseModel):
    id: UUID
    title: str
    summary: str
    edition_id: UUID | None
    member_count: int
    source_count: int
    first_seen_at: datetime
    last_activity_at: datetime
    last_change_kind: IssueChangeKind | None
    change_state: str
    tracking: bool
    has_unseen_change: bool


class IssueMemberRead(BaseModel):
    post_id: UUID
    title: str
    source_name: str
    board_type: BoardType
    role: str
    published_at: datetime | None
    original_url: str | None
    unverified: bool


class IssueRead(BaseModel):
    id: UUID
    title: str
    summary: str
    summary_confidence: str | None
    edition_id: UUID | None
    status: IssueStatus
    member_count: int
    source_count: int
    first_seen_at: datetime
    last_activity_at: datetime
    tracking: bool
    last_seen_at: datetime | None
    has_unseen_change: bool
    members: list[IssueMemberRead] = Field(default_factory=list)


class RevisionActor(BaseModel):
    user_id: UUID
    name: str


class IssueRevisionRead(BaseModel):
    id: UUID
    kind: IssueChangeKind
    fact_type: IssueFactType | None
    headline: str
    note: str
    post_id: UUID | None
    post_title: str | None
    source_name: str | None
    duplicate_post_ids: list[str] | None
    actor: RevisionActor | None
    occurred_at: datetime
    is_unseen: bool


class IssueChangeItem(BaseModel):
    id: UUID
    title: str
    edition_id: UUID | None
    last_activity_at: datetime
    new_revision_count: int
    top_change_kinds: list[str]
    new_member_count: int


class IssueChangesResponse(BaseModel):
    since: datetime | None
    items: list[IssueChangeItem]


class TrackingUpdateRequest(BaseModel):
    tracking: bool


class TrackingUpdateResponse(BaseModel):
    issue_id: UUID
    tracking: bool


class IssueMergeRequest(BaseModel):
    merge_with: UUID


class IssueSplitRequest(BaseModel):
    post_id: UUID
