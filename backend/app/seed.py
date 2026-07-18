import os

from pydantic import BaseModel, EmailStr, Field, ValidationError

from app.core.db import SessionLocal
from app.services.auth import create_initial_admin


class InitialAdminSettings(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


def seed_initial_admin() -> None:
    email = os.getenv("INITIAL_ADMIN_EMAIL")
    password = os.getenv("INITIAL_ADMIN_PASSWORD")
    if not email or not password:
        return
    try:
        payload = InitialAdminSettings(email=email, password=password)
    except ValidationError as exc:
        raise RuntimeError("Initial administrator settings are invalid") from exc

    with SessionLocal() as db:
        create_initial_admin(db, str(payload.email), payload.password)


if __name__ == "__main__":
    seed_initial_admin()
