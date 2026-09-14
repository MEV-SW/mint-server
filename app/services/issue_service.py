from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.enums import BoardType, IssueChangeKind, IssueStatus, PostStatus
from app.models.issue import Issue, IssueMember, IssueRevision, UserIssueSeen
from app.models.post import Post
from app.models.source import Source
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.issue import (
    IssueChangeItem,
    IssueChangesResponse,
    IssueListItem,
    IssueMemberRead,
    IssueRead,
    IssueRevisionRead,
    RevisionActor,
    TrackingUpdateResponse,
)
from app.services.membership_service import MembershipService

_CHANGE_STATE_TO_KIND = {
    "development": IssueChangeKind.development,
    "correction": IssueChangeKind.correction,
    "duplicates_only": IssueChangeKind.duplicates,
}
_QUIET_KINDS = (IssueChangeKind.first_report, IssueChangeKind.admin_adjust)


def _aware(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; PostgreSQL keeps it. Normalize to UTC-aware."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _derive_change_state(kind: IssueChangeKind | None) -> str:
    if kind == IssueChangeKind.development:
        return "development"
    if kind == IssueChangeKind.correction:
        return "correction"
    if kind == IssueChangeKind.duplicates:
        return "duplicates_only"
    return "quiet"


class IssueService:
    def __init__(self, db: Session):
        self.db = db

    def _visible_edition_ids(self, user: User) -> set[UUID] | None:
        return MembershipService(self.db).visible_edition_ids(user)

    def _edition_visible(self, edition_id: UUID | None, visible: set[UUID] | None) -> bool:
        if visible is None:
            return True
        return edition_id is None or edition_id in visible

    def _base_query(self, user: User, *, include_series: bool):
        excluded = [IssueStatus.merged]
        if not include_series:
            excluded.append(IssueStatus.series)
        return select(Issue).where(
            Issue.organization_id == user.organization_id,
            Issue.status.notin_(excluded),
        )

    def _tracking_map(self, user_id: UUID, issue_ids: list[UUID]) -> dict[UUID, UserIssueSeen]:
        if not issue_ids:
            return {}
        rows = self.db.scalars(
            select(UserIssueSeen).where(
                UserIssueSeen.user_id == user_id, UserIssueSeen.issue_id.in_(issue_ids)
            )
        ).all()
        return {row.issue_id: row for row in rows}

    def list_issues(
        self,
        user: User,
        *,
        page: int,
        size: int,
        filter: str = "all",
        edition_id: UUID | None = None,
        change_state: str | None = None,
        include_series: bool = False,
        search: str | None = None,
    ) -> PaginatedResponse[IssueListItem]:
        visible = self._visible_edition_ids(user)
        q = self._base_query(user, include_series=include_series)
        if edition_id is not None:
            q = q.where(Issue.edition_id == edition_id)
        if search:
            q = q.where(Issue.title.ilike(f"%{search.strip()}%"))
        if change_state is not None:
            if change_state == "quiet":
                q = q.where(
                    (Issue.last_change_kind.is_(None)) | (Issue.last_change_kind.in_(_QUIET_KINDS))
                )
            else:
                kind = _CHANGE_STATE_TO_KIND.get(change_state)
                q = q.where(Issue.last_change_kind == kind) if kind else q.where(False)

        rows = [row for row in self.db.scalars(q).all() if self._edition_visible(row.edition_id, visible)]

        if filter in ("tracked", "changed"):
            seen_map = self._tracking_map(user.id, [row.id for row in rows])
            tracked_rows = []
            for row in rows:
                seen = seen_map.get(row.id)
                if not seen or not seen.tracking:
                    continue
                if filter == "changed" and seen.last_seen_at and row.last_activity_at <= seen.last_seen_at:
                    continue
                tracked_rows.append(row)
            rows = tracked_rows

        rows.sort(key=lambda r: r.last_activity_at, reverse=True)
        total = len(rows)
        start = (page - 1) * size
        page_rows = rows[start : start + size]
        seen_map = self._tracking_map(user.id, [row.id for row in page_rows])

        items = []
        for row in page_rows:
            seen = seen_map.get(row.id)
            tracking = bool(seen and seen.tracking)
            has_unseen = bool(
                tracking and (not seen.last_seen_at or row.last_activity_at > seen.last_seen_at)
            )
            items.append(
                IssueListItem(
                    id=row.id,
                    title=row.title,
                    summary=row.summary,
                    edition_id=row.edition_id,
                    member_count=row.member_count,
                    source_count=row.source_count,
                    first_seen_at=row.first_seen_at,
                    last_activity_at=row.last_activity_at,
                    last_change_kind=row.last_change_kind,
                    change_state=_derive_change_state(row.last_change_kind),
                    tracking=tracking,
                    has_unseen_change=has_unseen,
                )
            )
        pages = (total + size - 1) // size if size else 0
        return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)

    def _get_visible_issue(self, user: User, issue_id: UUID) -> Issue:
        row = self.db.get(Issue, issue_id)
        if not row or row.organization_id != user.organization_id:
            raise NotFoundError("Issue not found")
        visible = self._visible_edition_ids(user)
        if not self._edition_visible(row.edition_id, visible):
            raise NotFoundError("Issue not found")
        if row.status == IssueStatus.merged:
            raise HTTPException(
                status_code=status.HTTP_308_PERMANENT_REDIRECT,
                headers={"Location": f"/api/v1/issues/{row.merged_into_id}"},
            )
        return row

    def get_issue(self, user: User, issue_id: UUID) -> IssueRead:
        row = self._get_visible_issue(user, issue_id)
        seen = self.db.scalar(
            select(UserIssueSeen).where(
                UserIssueSeen.user_id == user.id, UserIssueSeen.issue_id == row.id
            )
        )
        members = []
        for member, post, source in self.db.execute(
            select(IssueMember, Post, Source)
            .join(Post, Post.id == IssueMember.post_id)
            .outerjoin(Source, Source.id == Post.source_id)
            .where(
                IssueMember.issue_id == row.id,
                Post.organization_id == user.organization_id,
                Post.status.notin_((PostStatus.hidden, PostStatus.deleted)),
            )
            .order_by(Post.published_at.asc())
        ):
            members.append(
                IssueMemberRead(
                    post_id=post.id,
                    title=post.title,
                    source_name=source.name if source else "",
                    board_type=post.board_type,
                    role=member.role.value,
                    published_at=post.published_at,
                    original_url=post.original_url,
                    unverified=post.board_type == BoardType.discovery,
                )
            )
        tracking = bool(seen and seen.tracking)
        has_unseen = bool(
            tracking and (not seen.last_seen_at or row.last_activity_at > seen.last_seen_at)
        )
        return IssueRead(
            id=row.id,
            title=row.title,
            summary=row.summary,
            summary_confidence=None,
            edition_id=row.edition_id,
            status=row.status,
            member_count=row.member_count,
            source_count=row.source_count,
            first_seen_at=row.first_seen_at,
            last_activity_at=row.last_activity_at,
            tracking=tracking,
            last_seen_at=seen.last_seen_at if seen else None,
            has_unseen_change=has_unseen,
            members=members,
        )

    def list_revisions(
        self, user: User, issue_id: UUID, *, page: int, size: int
    ) -> PaginatedResponse[IssueRevisionRead]:
        row = self._get_visible_issue(user, issue_id)
        seen = self.db.scalar(
            select(UserIssueSeen).where(
                UserIssueSeen.user_id == user.id, UserIssueSeen.issue_id == row.id
            )
        )
        last_seen_at = seen.last_seen_at if seen else None

        q = (
            select(IssueRevision)
            .where(IssueRevision.issue_id == row.id)
            .order_by(IssueRevision.occurred_at.asc())
        )
        all_rows = list(self.db.scalars(q).all())
        total = len(all_rows)
        start = (page - 1) * size
        page_rows = all_rows[start : start + size]

        post_ids = [r.post_id for r in page_rows if r.post_id]
        posts_by_id: dict[UUID, Post] = {}
        sources_by_id: dict[UUID, Source] = {}
        if post_ids:
            for post in self.db.scalars(select(Post).where(Post.id.in_(post_ids))):
                posts_by_id[post.id] = post
            source_ids = [p.source_id for p in posts_by_id.values() if p.source_id]
            if source_ids:
                for source in self.db.scalars(select(Source).where(Source.id.in_(source_ids))):
                    sources_by_id[source.id] = source

        actor_ids = [r.actor_user_id for r in page_rows if r.actor_user_id]
        actors_by_id: dict[UUID, User] = {}
        if actor_ids:
            for actor in self.db.scalars(select(User).where(User.id.in_(actor_ids))):
                actors_by_id[actor.id] = actor

        items = []
        for r in page_rows:
            post = posts_by_id.get(r.post_id) if r.post_id else None
            source = sources_by_id.get(post.source_id) if post and post.source_id else None
            actor = actors_by_id.get(r.actor_user_id) if r.actor_user_id else None
            items.append(
                IssueRevisionRead(
                    id=r.id,
                    kind=r.kind,
                    fact_type=r.fact_type,
                    headline=r.headline,
                    note=r.note,
                    post_id=r.post_id,
                    post_title=post.title if post else None,
                    source_name=source.name if source else None,
                    original_url=post.original_url if post else None,
                    duplicate_post_ids=[str(pid) for pid in r.duplicate_post_ids] if r.duplicate_post_ids else None,
                    actor=RevisionActor(user_id=actor.id, name=actor.name) if actor else None,
                    occurred_at=r.occurred_at,
                    is_unseen=bool(last_seen_at is None or r.occurred_at > last_seen_at)
                    if last_seen_at is not None
                    else False,
                )
            )
        pages = (total + size - 1) // size if size else 0
        return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)

    def list_changes(self, user: User, *, since: datetime | None, limit: int) -> IssueChangesResponse:
        visible = self._visible_edition_ids(user)
        tracked = self.db.scalars(
            select(UserIssueSeen).where(
                UserIssueSeen.user_id == user.id, UserIssueSeen.tracking.is_(True)
            )
        ).all()
        if not tracked:
            return IssueChangesResponse(since=since, items=[])
        by_issue = {row.issue_id: row for row in tracked}
        issues = self.db.scalars(
            select(Issue).where(
                Issue.id.in_(by_issue.keys()),
                Issue.organization_id == user.organization_id,
                Issue.status == IssueStatus.active,
            )
        ).all()

        items = []
        for issue in issues:
            if not self._edition_visible(issue.edition_id, visible):
                continue
            seen = by_issue[issue.id]
            baseline = since or seen.last_seen_at
            if baseline and issue.last_activity_at <= baseline:
                continue
            revisions = self.db.scalars(
                select(IssueRevision)
                .where(IssueRevision.issue_id == issue.id)
                .where(IssueRevision.occurred_at > baseline if baseline else True)
                .order_by(IssueRevision.occurred_at.desc())
            ).all()
            top_kinds: list[str] = []
            for r in revisions:
                label = (r.fact_type.value if r.fact_type else r.kind.value)
                if label not in top_kinds:
                    top_kinds.append(label)
                if len(top_kinds) == 3:
                    break
            new_member_ids = self.db.scalars(
                select(IssueMember.id)
                .where(IssueMember.issue_id == issue.id)
                .where(IssueMember.added_at > baseline if baseline else True)
            ).all()
            items.append(
                IssueChangeItem(
                    id=issue.id,
                    title=issue.title,
                    edition_id=issue.edition_id,
                    last_activity_at=issue.last_activity_at,
                    new_revision_count=len(revisions),
                    top_change_kinds=top_kinds,
                    new_member_count=len(new_member_ids),
                )
            )
        items.sort(key=lambda i: i.last_activity_at, reverse=True)
        return IssueChangesResponse(since=since, items=items[:limit])

    def update_tracking(self, user: User, issue_id: UUID, tracking: bool) -> TrackingUpdateResponse:
        row = self.db.get(Issue, issue_id)
        if (
            not row
            or row.organization_id != user.organization_id
            or row.status == IssueStatus.merged
            or not self._edition_visible(row.edition_id, self._visible_edition_ids(user))
        ):
            raise NotFoundError("Issue not found")
        seen = self.db.scalar(
            select(UserIssueSeen).where(
                UserIssueSeen.user_id == user.id, UserIssueSeen.issue_id == issue_id
            )
        )
        if not seen:
            seen = UserIssueSeen(user_id=user.id, issue_id=issue_id, tracking=tracking)
            self.db.add(seen)
        else:
            seen.tracking = tracking
        self.db.commit()
        return TrackingUpdateResponse(issue_id=issue_id, tracking=tracking)

    def mark_seen(self, user: User, issue_id: UUID) -> None:
        self._get_visible_issue(user, issue_id)
        seen = self.db.scalar(
            select(UserIssueSeen).where(
                UserIssueSeen.user_id == user.id, UserIssueSeen.issue_id == issue_id
            )
        )
        now = datetime.now(timezone.utc)
        if not seen:
            seen = UserIssueSeen(user_id=user.id, issue_id=issue_id, tracking=True, last_seen_at=now)
            self.db.add(seen)
        else:
            seen.last_seen_at = now
        self.db.commit()

    def _load_admin_issue(self, user: User, issue_id: UUID) -> Issue:
        row = self.db.get(Issue, issue_id)
        if not row or row.organization_id != user.organization_id or row.status == IssueStatus.merged:
            raise NotFoundError("Issue not found")
        return row

    def _recount(self, issue: Issue) -> None:
        member_count = (
            self.db.scalar(
                select(func.count()).select_from(IssueMember).where(IssueMember.issue_id == issue.id)
            )
            or 0
        )
        source_count = (
            self.db.scalar(
                select(func.count(func.distinct(Post.source_id)))
                .select_from(IssueMember)
                .join(Post, Post.id == IssueMember.post_id)
                .where(IssueMember.issue_id == issue.id)
            )
            or 0
        )
        issue.member_count = member_count
        issue.source_count = source_count

    def merge_issue(self, user: User, issue_id: UUID, merge_with: UUID) -> IssueRead:
        if issue_id == merge_with:
            raise BadRequestError("자기 자신과는 병합할 수 없습니다.")
        target = self._load_admin_issue(user, issue_id)
        source = self._load_admin_issue(user, merge_with)

        self.db.execute(
            update(IssueMember).where(IssueMember.issue_id == source.id).values(issue_id=target.id)
        )
        source.status = IssueStatus.merged
        source.merged_into_id = target.id
        now = datetime.now(timezone.utc)
        target.last_activity_at = max(_aware(target.last_activity_at), _aware(source.last_activity_at), now)
        target.last_change_kind = IssueChangeKind.admin_adjust
        self.db.flush()
        self._recount(target)
        self.db.add(
            IssueRevision(
                issue_id=target.id,
                kind=IssueChangeKind.admin_adjust,
                headline=f'"{source.title}" 이슈를 병합',
                actor_user_id=user.id,
                occurred_at=now,
            )
        )
        self.db.commit()
        return self.get_issue(user, target.id)

    def split_issue(self, user: User, issue_id: UUID, post_id: UUID) -> IssueRead:
        source = self._load_admin_issue(user, issue_id)
        member = self.db.scalar(
            select(IssueMember).where(
                IssueMember.issue_id == source.id, IssueMember.post_id == post_id
            )
        )
        if not member:
            raise NotFoundError("Issue member not found")

        member_count = (
            self.db.scalar(
                select(func.count()).select_from(IssueMember).where(IssueMember.issue_id == source.id)
            )
            or 0
        )
        if member_count < 2:
            raise BadRequestError("구성 기사가 2건 미만이라 분리할 수 없습니다.")

        post = self.db.get(Post, post_id)
        now = datetime.now(timezone.utc)
        new_issue = Issue(
            organization_id=source.organization_id,
            edition_id=source.edition_id,
            title=post.title,
            status=IssueStatus.active,
            first_seen_at=post.published_at or now,
            last_activity_at=now,
            last_change_kind=IssueChangeKind.first_report,
        )
        self.db.add(new_issue)
        self.db.flush()

        member.issue_id = new_issue.id
        source.last_change_kind = IssueChangeKind.admin_adjust
        self.db.flush()
        self._recount(source)
        self._recount(new_issue)

        self.db.add(
            IssueRevision(
                issue_id=source.id,
                kind=IssueChangeKind.admin_adjust,
                headline=f'"{post.title}" 기사를 새 이슈로 분리',
                actor_user_id=user.id,
                occurred_at=now,
            )
        )
        self.db.add(
            IssueRevision(
                issue_id=new_issue.id,
                kind=IssueChangeKind.first_report,
                headline=post.title,
                post_id=post.id,
                occurred_at=post.published_at or now,
            )
        )
        self.db.commit()
        return self.get_issue(user, new_issue.id)
