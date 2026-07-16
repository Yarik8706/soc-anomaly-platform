from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenRead, UserRead
from app.services.audit import record_audit_event
from app.services.auth import authenticate, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenRead)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenRead:
    user = authenticate(db, str(payload.email), payload.password)
    if user is None:
        record_audit_event(
            db,
            None,
            "auth.login_failed",
            "user",
            str(payload.email).lower(),
            severity="warning",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    record_audit_event(db, user, "auth.login", "user", str(user.id))
    return TokenRead(
        access_token=create_access_token(user),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)
