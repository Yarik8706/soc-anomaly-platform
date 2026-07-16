import csv
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.auth import get_current_user
from app.services.log_normalization import (
    LogNormalizationError,
    NormalizationConfig,
    normalize_log_file,
)
from app.services.log_validation import validate_log_file
from app.services.uploads import normalize_uploaded_file


def test_validation_detects_columns_delimiter_and_cp1251(tmp_path: Path) -> None:
    input_path = tmp_path / "events.csv"
    input_path.write_bytes(
        "EventTime;Событие\n2026-07-15 12:00:00;Вход\n".encode("cp1251")
    )

    result = validate_log_file(input_path)

    assert result.is_valid is True
    assert result.encoding == "cp1251"
    assert result.delimiter == ";"
    assert result.columns == ("EventTime", "Событие")
    assert result.sampled_rows == 1
    assert result.errors == ()


def test_validation_reports_missing_critical_timestamp(tmp_path: Path) -> None:
    input_path = tmp_path / "events.csv"
    input_path.write_text("Name,Value\nlogin,1\n", encoding="utf-8")

    result = validate_log_file(input_path)

    assert result.is_valid is False
    assert result.columns == ("Name", "Value")
    assert result.missing_critical_columns == ("timestamp",)
    assert "Missing a timestamp column" in result.errors[0]


def test_normalization_creates_daily_siem_and_pan_artifacts(tmp_path: Path) -> None:
    input_path = tmp_path / "U.D.alice.tsv"
    output_directory = tmp_path / "normalized"
    input_path.write_text(
        "\t".join(
            (
                "Timestamp",
                "SourceUserName",
                "DestinationUserName",
                "Name",
                "DeviceProduct",
                "DeviceVendor",
                "ClusterID",
            )
        )
        + "\n"
        + "\n".join(
            (
                "2026-07-14T23:10:00\tDOMAIN\\alice\tbob@example.test\tLogin\tWindows\tMicrosoft\t1",
                "2026-07-15T08:00:00\talice\tcarol\tTRAFFIC\tPAN-OS\tPalo Alto Networks\t1",
                "2026-07-15T09:30:00\talice\tcarol\tLogin\tWindows\tMicrosoft\t1",
                "not-a-date\talice\tcarol\tLogin\tWindows\tMicrosoft\t1",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    result = normalize_log_file(
        NormalizationConfig(
            input_path=input_path,
            output_directory=output_directory,
        )
    )

    assert result.processed_rows == 3
    assert result.skipped_rows == 1
    assert {
        (artifact.date, artifact.source, artifact.rows) for artifact in result.artifacts
    } == {
        ("2026-07-14", "SIEM", 1),
        ("2026-07-15", "PAN", 1),
        ("2026-07-15", "SIEM", 1),
    }

    for artifact in result.artifacts:
        artifact_path = Path(artifact.path)
        assert artifact_path.parent == output_directory
        with artifact_path.open(encoding="utf-8", newline="") as output_file:
            rows = list(csv.DictReader(output_file))
        assert "ClusterID" not in rows[0]
        assert rows[0]["Date"] == artifact.date
        assert rows[0]["SourceUserName"] == "user001"

    with Path(result.user_mapping_path).open(
        encoding="utf-8", newline=""
    ) as mapping_file:
        mapping_rows = list(csv.DictReader(mapping_file))
    assert mapping_rows[0] == {"user_name": "alice", "userXXX": "user001"}


def test_normalization_rejects_invalid_structure(tmp_path: Path) -> None:
    input_path = tmp_path / "events.csv"
    input_path.write_text("Name,Value\nlogin,1\n", encoding="utf-8")

    with pytest.raises(LogNormalizationError, match="timestamp"):
        normalize_log_file(
            NormalizationConfig(
                input_path=input_path,
                output_directory=tmp_path / "normalized",
            )
        )


def test_normalization_result_is_saved_in_upload_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "HOST_server.csv"
    input_path.write_text(
        "Timestamp,Host,Name\n2026-07-15 10:30:00,server-01,Login\n",
        encoding="utf-8",
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    from app.services import uploads

    monkeypatch.setattr(uploads.settings, "normalized_directory", tmp_path / "results")
    with Session(engine) as db:
        uploaded_file = UploadedFile(
            filename=input_path.name,
            content_type="text/csv",
            size=input_path.stat().st_size,
            storage_path=str(input_path),
            status="pending",
        )
        db.add(uploaded_file)
        db.commit()
        db.refresh(uploaded_file)

        result = normalize_uploaded_file(db, uploaded_file)

        assert result.status == "normalized"
        assert result.validated_at is not None
        assert result.normalized_at is not None
        assert result.validation_result is not None
        assert result.validation_result["is_valid"] is True
        assert result.normalization_result is not None
        assert result.normalization_result["processed_rows"] == 1
        assert Path(result.normalization_result["artifacts"][0]["path"]).is_file()


def test_upload_api_exposes_validation_and_normalization_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "HOST_server.csv"
    input_path.write_text(
        "Timestamp,Host,Name\n2026-07-15 10:30:00,server-01,Login\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "database_url", "sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(settings, "normalized_directory", tmp_path / "results")

    from app.core.db import get_db
    from app.main import app

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        uploaded_file = UploadedFile(
            filename=input_path.name,
            content_type="text/csv",
            size=input_path.stat().st_size,
            storage_path=str(input_path),
            status="pending",
        )
        db.add(uploaded_file)
        db.commit()
        db.refresh(uploaded_file)
        file_id = str(uploaded_file.id)

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid4(),
        email="analyst@example.test",
        password_hash="unused",
        role="analyst",
        is_active=True,
    )
    try:
        with TestClient(app) as client:
            validation_response = client.post(f"/uploads/{file_id}/validate")
            normalization_response = client.post(f"/uploads/{file_id}/normalize")
            history_response = client.get("/uploads")
    finally:
        app.dependency_overrides.clear()

    assert validation_response.status_code == 200
    assert validation_response.json()["validation_result"]["is_valid"] is True
    assert normalization_response.status_code == 200
    assert normalization_response.json()["status"] == "normalized"
    assert len(normalization_response.json()["normalization_result"]["artifacts"]) == 1
    assert history_response.status_code == 200
    assert history_response.json()[0]["id"] == file_id
