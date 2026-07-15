from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.uploaded_file import UploadedFile
from app.services.log_normalization import (
    LogNormalizationError,
    NormalizationConfig,
    normalize_log_file,
)
from app.services.log_validation import FileValidationResult, validate_log_file

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt"}
MAX_FILE_SIZE = 50 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class InvalidFileTypeError(Exception):
    pass


class EmptyFileError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class InvalidLogStructureError(Exception):
    def __init__(self, result: FileValidationResult) -> None:
        self.result = result
        super().__init__("; ".join(result.errors))


async def save_uploaded_file(
    db: Session,
    file: UploadFile,
    uploaded_by: UUID | None = None,
    commit: bool = True,
) -> UploadedFile:

    if not file.filename:
        raise ValueError("Filename is required")

    original_filename = file.filename
    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(f"Unsupported file extension: {extension}")

    stored_filename = f"{uuid4()}{extension}"
    storage_path = settings.upload_directory / stored_filename

    settings.upload_directory.mkdir(parents=True, exist_ok=True)

    size = 0

    try:
        with storage_path.open("wb") as destination:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)

                if size > MAX_FILE_SIZE:
                    raise FileTooLargeError(
                        f"File exceeds the {MAX_FILE_SIZE} byte limit"
                    )

                destination.write(chunk)

        if size == 0:
            raise EmptyFileError("File is empty")

        uploaded_file = UploadedFile(
            filename=original_filename,
            content_type=file.content_type or "application/octet-stream",
            size=size,
            storage_path=str(storage_path),
            status="pending",
            uploaded_by=uploaded_by,
        )

        db.add(uploaded_file)

        if commit:
            db.commit()
            db.refresh(uploaded_file)
        else:
            db.flush()

        return uploaded_file

    except Exception:
        db.rollback()
        storage_path.unlink(missing_ok=True)
        raise


async def save_uploaded_files(
    db: Session,
    files: list[UploadFile],
    uploaded_by: UUID | None = None,
) -> list[UploadedFile]:
    if not files:
        raise ValueError("At least one file is required")

    if len(files) > 10:
        raise ValueError("A maximum of 10 files can be uploaded at once")

    uploaded_files: list[UploadedFile] = []

    try:
        for file in files:
            uploaded_file = await save_uploaded_file(
                db=db,
                file=file,
                uploaded_by=uploaded_by,
                commit=False,
            )
            uploaded_files.append(uploaded_file)

        db.commit()

    except Exception:
        db.rollback()

        for uploaded_file in uploaded_files:
            Path(uploaded_file.storage_path).unlink(missing_ok=True)

        raise

    for uploaded_file in uploaded_files:
        db.refresh(uploaded_file)

    return uploaded_files


def list_uploaded_files(db: Session) -> list[UploadedFile]:
    statement = select(UploadedFile).order_by(UploadedFile.created_at.desc())
    return list(db.scalars(statement).all())


def get_uploaded_file(db: Session, file_id: UUID) -> UploadedFile | None:
    return db.get(UploadedFile, file_id)


def validate_uploaded_file(
    db: Session,
    uploaded_file: UploadedFile,
) -> UploadedFile:
    result = validate_log_file(Path(uploaded_file.storage_path))
    uploaded_file.validation_result = result.to_dict()
    uploaded_file.validated_at = _utc_now()
    uploaded_file.status = "validated" if result.is_valid else "invalid"
    db.commit()
    db.refresh(uploaded_file)
    return uploaded_file


def normalize_uploaded_file(
    db: Session,
    uploaded_file: UploadedFile,
) -> UploadedFile:
    validation = validate_log_file(Path(uploaded_file.storage_path))
    uploaded_file.validation_result = validation.to_dict()
    uploaded_file.validated_at = _utc_now()

    if not validation.is_valid:
        uploaded_file.status = "invalid"
        db.commit()
        db.refresh(uploaded_file)
        raise InvalidLogStructureError(validation)

    output_directory = (
        settings.normalized_directory
        / str(uploaded_file.id)
        / _utc_now().strftime("%Y%m%dT%H%M%S%f")
    )
    try:
        result = normalize_log_file(
            NormalizationConfig(
                input_path=Path(uploaded_file.storage_path),
                output_directory=output_directory,
            ),
            validation=validation,
        )
    except LogNormalizationError as exc:
        uploaded_file.status = "failed"
        uploaded_file.normalization_result = {"errors": [str(exc)]}
        db.commit()
        db.refresh(uploaded_file)
        raise

    uploaded_file.normalization_result = result.to_dict()
    uploaded_file.normalized_at = _utc_now()
    uploaded_file.status = "normalized"
    db.commit()
    db.refresh(uploaded_file)
    return uploaded_file


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
