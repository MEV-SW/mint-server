from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.enums import UserRole
from app.models.user import User
from app.services.membership_service import MembershipService, is_org_admin

ADMIN_ROLES = {UserRole.admin}
WRITE_ROLES = {UserRole.admin}
INQUIRY_SUBMIT_ROLES = {UserRole.manager, UserRole.member, UserRole.viewer}
SOURCE_REVIEW_ROLES = {UserRole.admin, UserRole.manager}


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user


def require_source_reviewer(user: User = Depends(get_current_user)) -> User:
    if user.role not in SOURCE_REVIEW_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 또는 매니저만 사용할 수 있습니다.",
        )
    return user


def require_inquiry_submitter(user: User = Depends(get_current_user)) -> User:
    if user.role not in INQUIRY_SUBMIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user


def require_edition_editor_any(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    MembershipService(db).assert_editor_any(user)
    return user


def require_edition_editor(
    edition_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    MembershipService(db).assert_editor(user, edition_id)
    return user


__all__ = [
    "ADMIN_ROLES",
    "WRITE_ROLES",
    "INQUIRY_SUBMIT_ROLES",
    "SOURCE_REVIEW_ROLES",
    "is_org_admin",
    "require_admin",
    "require_source_reviewer",
    "require_inquiry_submitter",
    "require_edition_editor",
    "require_edition_editor_any",
]
