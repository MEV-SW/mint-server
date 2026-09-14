"""B4 — assign a newly-crawled post to an existing issue, or start a new one.

Called once per post from the shared crawl hook
(CrawlerService._attach_discovery_ai_output, after save_post_content so the
post's embedding already exists in ES). Never raises into the crawl path —
callers should still wrap this in try/except; issue assignment is additive,
crawling is not allowed to break because of it.

Thresholds are provisional (B2 experiment, not B3-confirmed) — see
app/core/config.py Settings.issue_near_dup_cosine/issue_event_cosine and
scripts/experiments/issue_clustering/README.md.

Series guard is a simplified proxy: an issue whose every member so far comes
from a single source (source_count == 1) once it has 3+ members reads as a
recurring single-outlet notice (daily bulletin, template press release)
rather than a multi-source-covered event, so it's marked `series` and
excluded from tracking/changes. This is narrower than "정기 주기" (regular
interval) in the B4 issue text — regularity detection needs more sample
density than the current corpus has; revisit once B3's real distribution
data is in.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import IssueChangeKind, IssueFactType, IssueMemberRole, IssueStatus
from app.models.issue import Issue, IssueMember, IssueRevision
from app.models.post import Post
from app.search.post_content import get_post_content
from app.search.post_search import get_post_embedding, knn_similar_post_ids
from app.services.issue_service import recount_issue

logger = logging.getLogger(__name__)

_SERIES_MIN_MEMBERS = 3


class IssueAssignmentService:
    def __init__(self, db: Session):
        self.db = db

    def assign_post(self, post: Post) -> Issue | None:
        settings = get_settings()
        if not settings.issue_radar_enabled:
            return None
        if not post.published_at:
            return None

        embedding = get_post_embedding(post.id)
        if not embedding:
            logger.debug("no embedding yet for post %s, skipping issue assignment", post.id)
            return None

        window = timedelta(days=settings.issue_window_days)
        candidates = knn_similar_post_ids(
            post.organization_id,
            post.id,
            embedding,
            since=post.published_at - window,
            until=post.published_at + window,
        )

        match = self._best_match(post, candidates, settings.issue_near_dup_cosine, settings.issue_event_cosine)
        if match is not None:
            issue, score, role, kind = match
            self._join_issue(post, issue, score, role, kind)
            return issue
        return self._create_issue(post)

    def _best_match(
        self,
        post: Post,
        candidates: list[tuple[UUID, float]],
        near_dup_cosine: float,
        event_cosine: float,
    ) -> tuple[Issue, float, IssueMemberRole, IssueChangeKind] | None:
        if not candidates:
            return None
        candidate_ids = [pid for pid, _score in candidates]
        members = self.db.scalars(
            select(IssueMember).where(IssueMember.post_id.in_(candidate_ids))
        ).all()
        issue_by_post: dict[UUID, UUID] = {m.post_id: m.issue_id for m in members}
        if not issue_by_post:
            return None
        issue_ids = set(issue_by_post.values())
        issues = self.db.scalars(select(Issue).where(Issue.id.in_(issue_ids))).all()
        issue_by_id = {i.id: i for i in issues}

        for post_id, score in candidates:  # already sorted by ES score desc
            issue_id = issue_by_post.get(post_id)
            if not issue_id:
                continue
            issue = issue_by_id.get(issue_id)
            if not issue or issue.organization_id != post.organization_id:
                continue
            if issue.status == IssueStatus.merged:
                continue
            if score >= near_dup_cosine:
                return issue, score, IssueMemberRole.duplicate, IssueChangeKind.duplicates
            if score >= event_cosine:
                return issue, score, IssueMemberRole.development, IssueChangeKind.development
        return None

    def _join_issue(
        self, post: Post, issue: Issue, score: float, role: IssueMemberRole, kind: IssueChangeKind
    ) -> None:
        headline = post.title
        fact_type: IssueFactType | None = None
        note = ""
        if kind == IssueChangeKind.development:
            # near-dup(duplicates)은 B2 임계값만으로 이미 "중복으로 접힘" —
            # AI 분류(B5)는 실질 변화(development) 판정에서만 돌린다.
            headline, note, fact_type = self._classify_change(post, issue)
            issue.summary = headline  # "AI 요약(B5가 갱신)" — 최신 전개로 갱신

        self.db.add(
            IssueMember(issue_id=issue.id, post_id=post.id, role=role, similarity=score)
        )
        self.db.add(
            IssueRevision(
                issue_id=issue.id,
                kind=kind,
                fact_type=fact_type,
                headline=headline,
                note=note,
                post_id=post.id,
                prompt_version="issue_change_v1" if kind == IssueChangeKind.development else "",
                occurred_at=post.published_at,
            )
        )
        if post.published_at > issue.last_activity_at:
            issue.last_activity_at = post.published_at
        issue.last_change_kind = kind
        self.db.flush()
        recount_issue(self.db, issue)
        self._apply_series_guard(issue)

    def _classify_change(self, post: Post, issue: Issue) -> tuple[str, str, IssueFactType | None]:
        """B5 — ask the LLM what this development adds to the issue. Falls back
        to the plain post title (no fact_type) on any failure — assignment
        must not fail just because classification did."""
        try:
            from app.services.llm_client import get_llm_client

            content = get_post_content(self.db, post.id)
            result = get_llm_client().classify_issue_change(
                issue.title, issue.summary or "", post.title, content.body or ""
            )
            headline = (result.get("headline") or post.title).strip()[:512]
            note = (result.get("note") or "").strip()
            fact_type = IssueFactType(result.get("fact_type")) if result.get("fact_type") else None
            return headline, note, fact_type
        except Exception as exc:
            logger.warning("issue change classification failed for post %s: %s", post.id, exc)
            return post.title, "", None
        self.db.commit()

    def _create_issue(self, post: Post) -> Issue:
        issue = Issue(
            organization_id=post.organization_id,
            title=post.title,
            status=IssueStatus.active,
            member_count=1,
            source_count=1,
            first_seen_at=post.published_at,
            last_activity_at=post.published_at,
            last_change_kind=IssueChangeKind.first_report,
        )
        self.db.add(issue)
        self.db.flush()
        self.db.add(
            IssueMember(issue_id=issue.id, post_id=post.id, role=IssueMemberRole.origin, similarity=1.0)
        )
        self.db.add(
            IssueRevision(
                issue_id=issue.id,
                kind=IssueChangeKind.first_report,
                post_id=post.id,
                headline=post.title,
                occurred_at=post.published_at,
            )
        )
        self.db.commit()
        return issue

    def _apply_series_guard(self, issue: Issue) -> None:
        if issue.status != IssueStatus.active:
            return
        if issue.member_count >= _SERIES_MIN_MEMBERS and issue.source_count == 1:
            issue.status = IssueStatus.series
