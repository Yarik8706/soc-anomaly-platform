from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.user import User
from app.seed import seed_initial_admin
from app.services.auth import authenticate


def test_initial_admin_seed_is_idempotent(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    from app import seed

    monkeypatch.setattr(seed, "SessionLocal", factory)
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@admin.com")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "admin")

    seed_initial_admin()
    seed_initial_admin()

    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        admin = db.scalar(select(User))
        assert admin is not None
        assert admin.role == "admin"
        assert authenticate(db, "admin@admin.com", "admin") == admin
