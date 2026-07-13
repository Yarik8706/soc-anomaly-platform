from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.uploads import UploadedFileRead
from app.services.uploads import (
    EmptyFileError,
    FileTooLargeError,
    InvalidFileTypeError,
    save_uploaded_file,
    save_uploaded_files,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post(
    "",
    response_model=UploadedFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadedFileRead:
    try:
        uploaded_file = await save_uploaded_file(
            db=db,
            file=file,
            uploaded_by=None,
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
) -> list[UploadedFileRead]:
    try:
        uploaded_files = await save_uploaded_files(
            db=db,
            files=files,
            uploaded_by=None,
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
