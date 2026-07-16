from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.db.base import Base
from app.main import app
from app.schemas.auth import UserCreate
from app.services.auth import create_user


def _engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_login_rbac_user_management_and_admin_audit_log() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        create_user(
            db,
            UserCreate(
                email="admin@example.com",
                password="correct-horse-battery-staple",
                role="admin",
            ),
        )
        create_user(
            db,
            UserCreate(
                email="viewer@example.com",
                password="viewer-password-long",
                role="viewer",
            ),
        )

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            anonymous = client.get("/anomalies")
            invalid = client.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "wrong-password"},
            )
            admin_login = client.post(
                "/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": "correct-horse-battery-staple",
                },
            )
            viewer_login = client.post(
                "/auth/login",
                json={
                    "email": "viewer@example.com",
                    "password": "viewer-password-long",
                },
            )
            admin_headers = {
                "Authorization": f"Bearer {admin_login.json()['access_token']}"
            }
            viewer_headers = {
                "Authorization": f"Bearer {viewer_login.json()['access_token']}"
            }
            me = client.get("/auth/me", headers=admin_headers)
            forbidden = client.get("/users", headers=viewer_headers)
            created = client.post(
                "/users",
                headers=admin_headers,
                json={
                    "email": "analyst@example.com",
                    "password": "analyst-password-long",
                    "role": "analyst",
                },
            )
            audit = client.get("/audit", headers=admin_headers)
    finally:
        app.dependency_overrides.clear()

    assert anonymous.status_code == 401
    assert invalid.status_code == 401
    assert admin_login.status_code == 200
    assert me.json()["role"] == "admin"
    assert forbidden.status_code == 403
    assert created.status_code == 201
    assert created.json()["role"] == "analyst"
    assert audit.status_code == 200
    assert audit.json()["items"][0]["action"] == "user.create"
