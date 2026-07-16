import os

from pydantic import ValidationError

from app.core.db import SessionLocal
from app.schemas.auth import UserCreate, UserRole
from app.services.auth import create_user, get_user_by_email


def seed_initial_admin() -> None:
    email = os.getenv("INITIAL_ADMIN_EMAIL")
    password = os.getenv("INITIAL_ADMIN_PASSWORD")
    if not email or not password:
        return
    try:
        payload = UserCreate(email=email, password=password, role=UserRole.admin)
    except ValidationError as exc:
        raise RuntimeError("Initial administrator settings are invalid") from exc

    with SessionLocal() as db:
        if get_user_by_email(db, str(payload.email)) is None:
            create_user(db, payload)


if __name__ == "__main__":
    seed_initial_admin()
