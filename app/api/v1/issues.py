from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_admin
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.issue import (
    IssueChangesResponse,
    IssueListItem,
    IssueMergeRequest,
    IssueRead,
    IssueRevisionRead,
    IssueSplitRequest,
    TrackingUpdateRequest,
    TrackingUpdateResponse,
)
from app.services.issue_service import IssueService

router = APIRouter()


@router.get("", response_model=PaginatedResponse[IssueListItem])
def list_issues(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    filter: str = Query("all"),
    edition_id: UUID | None = None,
    change_state: str | None = None,
    include_series: bool = Query(False),
    q: str | None = Query(None, description="제목 부분 검색 (관리자 병합·분리 화면)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return IssueService(db).list_issues(
        user,
        page=page,
        size=size,
        filter=filter,
        edition_id=edition_id,
        change_state=change_state,
        include_series=include_series,
        search=q,
    )


@router.get("/changes", response_model=IssueChangesResponse)
def list_issue_changes(
    since: datetime | None = None,
    limit: int = Query(20, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return IssueService(db).list_changes(user, since=since, limit=limit)


@router.get("/{issue_id}", response_model=IssueRead)
def get_issue(issue_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return IssueService(db).get_issue(user, issue_id)


@router.get("/{issue_id}/revisions", response_model=PaginatedResponse[IssueRevisionRead])
def list_issue_revisions(
    issue_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return IssueService(db).list_revisions(user, issue_id, page=page, size=size)


@router.put("/{issue_id}/tracking", response_model=TrackingUpdateResponse)
def update_issue_tracking(
    issue_id: UUID,
    data: TrackingUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return IssueService(db).update_tracking(user, issue_id, data.tracking)


@router.post("/{issue_id}/seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_issue_seen(
    issue_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    IssueService(db).mark_seen(user, issue_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{issue_id}/merge", response_model=IssueRead)
def merge_issue(
    issue_id: UUID,
    data: IssueMergeRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return IssueService(db).merge_issue(user, issue_id, data.merge_with)


@router.post("/{issue_id}/split", response_model=IssueRead)
def split_issue(
    issue_id: UUID,
    data: IssueSplitRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return IssueService(db).split_issue(user, issue_id, data.post_id)
