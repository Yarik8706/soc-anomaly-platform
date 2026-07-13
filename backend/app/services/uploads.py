from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.uploaded_file import UploadedFile

UPLOAD_DIRECTORY = Path("/app/data/uploads")
ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt"}
MAX_FILE_SIZE = 50 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class InvalidFileTypeError(Exception):
    pass


class EmptyFileError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


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
    storage_path = UPLOAD_DIRECTORY / stored_filename

    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)

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
