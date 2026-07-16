from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.user import User
from app.models.uploaded_file import UploadedFile
from app.schemas.uploads import UploadedFileRead
from app.schemas.auth import UserRole
from app.services.audit import record_audit_event
from app.services.auth import require_roles
from app.services.uploads import (
    EmptyFileError,
    FileTooLargeError,
    InvalidLogStructureError,
    InvalidFileTypeError,
    get_uploaded_file,
    list_uploaded_files,
    normalize_uploaded_file,
    save_uploaded_file,
    save_uploaded_files,
    validate_uploaded_file,
)
from app.services.log_normalization import LogNormalizationError

router = APIRouter(
    prefix="/uploads",
    tags=["uploads"],
    dependencies=[Depends(require_roles(*UserRole))],
)
write_required = require_roles(UserRole.admin, UserRole.analyst)


@router.get("", response_model=list[UploadedFileRead])
def get_uploads(db: Session = Depends(get_db)) -> list[UploadedFileRead]:
    return [
        UploadedFileRead.model_validate(uploaded_file)
        for uploaded_file in list_uploaded_files(db)
    ]


@router.post(
    "",
    response_model=UploadedFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(write_required),
) -> UploadedFileRead:
    try:
        uploaded_file = await save_uploaded_file(
            db=db,
            file=file,
            uploaded_by=user.id,
        )
        record_audit_event(
            db,
            user,
            "upload.create",
            "uploaded_file",
            str(uploaded_file.id),
            details={"filename": uploaded_file.filename, "size": uploaded_file.size},
        )
        return UploadedFileRead.model_validate(uploaded_file)

    except InvalidFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except EmptyFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    finally:
        await file.close()


@router.post(
    "/batch",
    response_model=list[UploadedFileRead],
    status_code=status.HTTP_201_CREATED,
)
async def upload_files(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(write_required),
) -> list[UploadedFileRead]:
    try:
        uploaded_files = await save_uploaded_files(
            db=db,
            files=files,
            uploaded_by=user.id,
        )
        for uploaded_file in uploaded_files:
            record_audit_event(
                db,
                user,
                "upload.create",
                "uploaded_file",
                str(uploaded_file.id),
                details={"filename": uploaded_file.filename, "size": uploaded_file.size},
            )

        return [
            UploadedFileRead.model_validate(uploaded_file)
            for uploaded_file in uploaded_files
        ]

    except InvalidFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except EmptyFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    finally:
        for file in files:
            await file.close()


@router.get("/{file_id}", response_model=UploadedFileRead)
def get_upload(
    file_id: UUID,
    db: Session = Depends(get_db),
) -> UploadedFileRead:
    uploaded_file = _get_upload_or_404(db, file_id)
    return UploadedFileRead.model_validate(uploaded_file)


@router.post("/{file_id}/validate", response_model=UploadedFileRead)
def validate_upload(
    file_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(write_required),
) -> UploadedFileRead:
    uploaded_file = _get_upload_or_404(db, file_id)
    try:
        result = validate_uploaded_file(db, uploaded_file)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unable to read uploaded file: {exc}",
        ) from exc
    return UploadedFileRead.model_validate(result)


@router.post("/{file_id}/normalize", response_model=UploadedFileRead)
def normalize_upload(
    file_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(write_required),
) -> UploadedFileRead:
    uploaded_file = _get_upload_or_404(db, file_id)
    try:
        result = normalize_uploaded_file(db, uploaded_file)
    except InvalidLogStructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.result.to_dict(),
        ) from exc
    except (LogNormalizationError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return UploadedFileRead.model_validate(result)


def _get_upload_or_404(db: Session, file_id: UUID) -> UploadedFile:
    uploaded_file = get_uploaded_file(db, file_id)
    if uploaded_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded file not found",
        )
    return uploaded_file
