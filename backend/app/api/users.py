from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.user import User
from app.schemas.auth import UserCreate, UserRead, UserRole, UserUpdate
from app.services.audit import record_audit_event
from app.services.auth import create_user, list_users, require_roles, update_user

router = APIRouter(prefix="/users", tags=["users"])
admin_required = require_roles(UserRole.admin)


@router.get("", response_model=list[UserRead])
def get_users(
    db: Session = Depends(get_db), admin: User = Depends(admin_required)
) -> list[UserRead]:
    return [UserRead.model_validate(user) for user in list_users(db)]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def add_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
) -> UserRead:
    try:
        user = create_user(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    record_audit_event(
        db,
        admin,
        "user.create",
        "user",
        str(user.id),
        severity="critical" if user.role == "admin" else "info",
        details={"role": user.role},
    )
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
def edit_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
) -> UserRead:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    updated = update_user(db, user, payload)
    record_audit_event(
        db,
        admin,
        "user.update",
        "user",
        str(user.id),
        severity="critical" if payload.role == UserRole.admin else "info",
        details=payload.model_dump(mode="json", exclude_none=True, exclude={"password"}),
    )
    return UserRead.model_validate(updated)
