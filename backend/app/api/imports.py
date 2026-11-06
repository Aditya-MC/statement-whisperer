"""Upload and import-status endpoints.

Uploads are read into memory and the upload handle is closed in `finally`. Starlette spools
large uploads to a temporary file, and closing the handle deletes it. We never write uploads
to disk ourselves.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_llm
from app.config import get_settings
from app.db import get_db
from app.ingestion.detect import UnsupportedFileError
from app.ingestion.pipeline import DuplicateFileError, FileMismatchError, ingest
from app.models import Account, Import, ImportStatus
from app.schemas.api import ErrorOut, ImportOut
from app.schemas.mapping import ColumnMapping
from app.services.llm import LLMClient

router = APIRouter(tags=["imports"])

_ERRORS: dict[int | str, dict[str, object]] = {
    409: {"model": ErrorOut, "description": "File already imported into this account"},
    413: {"model": ErrorOut, "description": "File too large"},
    415: {"model": ErrorOut, "description": "Unsupported file type"},
}


async def _read_upload(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_bytes
    try:
        data = await file.read(limit + 1)
    finally:
        await file.close()
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty file")
    return data


def _parse_mapping(raw: str | None) -> ColumnMapping | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return ColumnMapping.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        detail = (
            exc.errors(include_input=False) if isinstance(exc, ValidationError) else "Invalid JSON"
        )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail) from exc


def _run_ingest(
    db: Session,
    llm: LLMClient,
    account: Account,
    data: bytes,
    filename: str | None,
    mapping: ColumnMapping | None,
    existing: Import | None = None,
) -> Import | JSONResponse:
    try:
        return ingest(db, llm, account, data, filename, mapping_override=mapping, existing=existing)
    except UnsupportedFileError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except FileMismatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except DuplicateFileError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorOut(
                detail=str(exc), existing_import_id=exc.existing_import_id
            ).model_dump(),
        )


@router.post(
    "/imports",
    response_model=ImportOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
)
async def create_import(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    mapping: str | None = Form(
        default=None, description="Optional ColumnMapping JSON to skip automatic detection."
    ),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
) -> Import | JSONResponse:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    override = _parse_mapping(mapping)
    filename = file.filename
    data = await _read_upload(file)
    return await run_in_threadpool(_run_ingest, db, llm, account, data, filename, override)


@router.post("/imports/{import_id}/retry", response_model=ImportOut, responses=_ERRORS)
async def retry_import(
    import_id: int,
    file: UploadFile = File(..., description="The same statement file as the original upload."),
    mapping: str | None = Form(default=None, description="Corrected ColumnMapping JSON."),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
) -> Import | JSONResponse:
    """Re-run an import that needs review, usually with a corrected column mapping.

    The original file must be uploaded again because uploads are never kept on the server.
    """
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    if imp.status == ImportStatus.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Import already completed")
    account = db.get(Account, imp.account_id)
    assert account is not None
    override = _parse_mapping(mapping)
    filename = file.filename
    data = await _read_upload(file)
    return await run_in_threadpool(
        _run_ingest, db, llm, account, data, filename, override, existing=imp
    )


@router.get("/imports/{import_id}", response_model=ImportOut)
def get_import(import_id: int, db: Session = Depends(get_db)) -> Import:
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    return imp


@router.get("/imports", response_model=list[ImportOut])
def list_imports(account_id: int | None = None, db: Session = Depends(get_db)) -> list[Import]:
    stmt = select(Import).order_by(Import.id.desc())
    if account_id is not None:
        stmt = stmt.where(Import.account_id == account_id)
    return list(db.scalars(stmt))
