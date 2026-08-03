"""
Document endpoints.

    POST   /api/documents/upload
    GET    /api/documents
    GET    /api/documents/{id}
    DELETE /api/documents/{id}
    GET    /api/documents/{id}/download
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional

from beanie import PydanticObjectId
from fastapi import (
    APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status,
)
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.deps import CurrentUser
from app.models.document import Document
from app.models.enums import (
    AuditAction,
    AuditStatus,
    DocumentType,
    ProcessingStatus,
    UserRole,
)
from app.models.report import ParsedReport
from app.models.user import User
from app.schemas.common import Message, PaginatedResponse
from app.schemas.document import DocumentOut, UploadResponse
from app.services.audit_service import log_action
from app.utils.file_utils import (
    FileValidationError,
    build_storage_path,
    compute_file_hash,
    safe_display_name,
    validate_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a financial document for parsing",
)
async def upload_document(
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="PDF, JPG, JPEG or PNG, max 25 MB")],
):
    """
    Validates the file, stores it, and records it ready for parsing.

    Returns 201 immediately - the heavy AI work happens in the background so
    the request doesn't hang for the 5-15 seconds an AI call can take.
    """
    content = await file.read()

    # --- Rule checks: type, size, emptiness, corruption, encryption ---
    try:
        mime_type = validate_upload(file.filename or "", content)
    except FileValidationError as exc:
        await log_action(
            AuditAction.DOCUMENT_UPLOADED,
            status=AuditStatus.FAILURE,
            user=user,
            remarks=f"Rejected: {exc.message}",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": exc.message, "code": exc.code},
        ) from exc

    # --- Duplicate detection by content hash, scoped to this user ---
    file_hash = compute_file_hash(content)
    duplicate = await Document.find_one(
        Document.uploaded_by == str(user.id),
        Document.file_hash == file_hash,
    )
    if duplicate:
        await log_action(
            AuditAction.DOCUMENT_UPLOADED,
            status=AuditStatus.FAILURE,
            user=user,
            document_id=str(duplicate.id),
            remarks="Duplicate upload blocked",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "You have already uploaded this exact file",
                "code": "duplicate_document",
                "existing_document_id": str(duplicate.id),
                "existing_document_name": duplicate.document_name,
                "uploaded_at": duplicate.created_at.isoformat(),
            },
        )

    # --- Persist to disk ---
    storage_path, _stored_name = build_storage_path(file.filename or "upload.pdf")
    try:
        storage_path.write_bytes(content)
    except OSError as exc:
        logger.exception("Failed writing upload to disk")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the uploaded file",
        ) from exc

    document = Document(
        document_name=safe_display_name(file.filename or "upload.pdf"),
        file_path=str(storage_path),
        file_size=len(content),
        mime_type=mime_type,
        file_hash=file_hash,
        uploaded_by=str(user.id),
        uploader_name=user.name,
        uploader_email=user.email,
        status=ProcessingStatus.UPLOADED,
    )

    try:
        await document.insert()
    except Exception:
        # Remove the orphaned file so disk and database don't drift apart.
        storage_path.unlink(missing_ok=True)
        raise

    await log_action(
        AuditAction.DOCUMENT_UPLOADED,
        user=user,
        document_id=str(document.id),
        document_name=document.document_name,
        remarks=f"{document.document_name} ({len(content)} bytes)",
    )

    # Kick off OCR + parsing without making the client wait for it.
    from app.api.parser import _run_pipeline_in_background

    background_tasks.add_task(_run_pipeline_in_background, str(document.id), user)

    # Kick off OCR + parsing without making the client wait for it.
    from app.api.parser import _run_pipeline_in_background

    background_tasks.add_task(_run_pipeline_in_background, str(document.id), user)

    return UploadResponse(
        document=DocumentOut.from_document(document),
        processing_id=str(document.id),
        message="Upload accepted. Processing has been queued.",
    )


@router.get(
    "",
    response_model=PaginatedResponse[DocumentOut],
    summary="List documents with search, filters and pagination",
)
async def list_documents(
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Filename or extracted field value"),
    document_type: Optional[DocumentType] = None,
    processing_status: Optional[ProcessingStatus] = Query(None, alias="status"),
    uploaded_by: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    min_processing_time: Optional[float] = None,
    max_processing_time: Optional[float] = None,
):
    query: dict[str, Any] = {}

    # Analysts only see their own uploads; admins see everything.
    if user.role != UserRole.ADMIN:
        query["uploaded_by"] = str(user.id)
    elif uploaded_by:
        query["uploaded_by"] = uploaded_by

    if document_type:
        query["document_type"] = document_type.value
    if processing_status:
        query["status"] = processing_status.value

    if date_from or date_to:
        created: dict[str, datetime] = {}
        if date_from:
            created["$gte"] = date_from
        if date_to:
            created["$lte"] = date_to
        query["created_at"] = created

    if min_processing_time is not None or max_processing_time is not None:
        pt: dict[str, float] = {}
        if min_processing_time is not None:
            pt["$gte"] = min_processing_time
        if max_processing_time is not None:
            pt["$lte"] = max_processing_time
        query["processing_time"] = pt

    if search:
        escaped = _escape_regex(search.strip())
        matching_ids = await _document_ids_matching_extracted_fields(escaped)

        or_clauses: list[dict[str, Any]] = [
            {"document_name": {"$regex": escaped, "$options": "i"}}
        ]
        if matching_ids:
            or_clauses.append({"_id": {"$in": matching_ids}})
        query["$or"] = or_clauses

    total = await Document.find(query).count()

    documents = (
        await Document.find(query)
        .sort("-created_at")
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )

    return PaginatedResponse.create(
        items=[DocumentOut.from_document(d) for d in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


def _escape_regex(term: str) -> str:
    """
    Escape regex metacharacters in user input.

    Without this, a search for "a{1,99999}" becomes a catastrophic-backtracking
    denial of service, and "." matches everything. User input must never reach
    a regex engine unescaped.
    """
    return re.escape(term)


async def _document_ids_matching_extracted_fields(escaped_term: str) -> list:
    """
    Find documents whose parsed fields contain the search term.

    Mongo cannot regex-search across arbitrary nested keys directly, so we run
    an aggregation that flattens each report's parsed_data to a string and
    matches against that.
    """
    pipeline = [
        {
            "$addFields": {
                "_searchable": {
                    "$concat": [
                        {"$ifNull": [{"$toString": "$parsed_data"}, ""]},
                        " ",
                        {"$ifNull": [{"$toString": "$corrected_data"}, ""]},
                    ]
                }
            }
        },
        {"$match": {"_searchable": {"$regex": escaped_term, "$options": "i"}}},
        {"$project": {"document_id": 1}},
        {"$limit": 500},
    ]

    try:
        rows = await ParsedReport.aggregate(pipeline).to_list()
    except Exception:
        logger.warning("Extracted-field search failed, falling back to filename only")
        return []

    ids = []
    for row in rows:
        try:
            ids.append(PydanticObjectId(row["document_id"]))
        except Exception:
            continue
    return ids


async def _get_document_or_404(document_id: str, user: User) -> Document:
    try:
        object_id = PydanticObjectId(document_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    document = await Document.get(object_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if user.role != UserRole.ADMIN and document.uploaded_by != str(user.id):
        # 404 rather than 403 so the existence of other users' documents isn't
        # leaked to anyone probing ids.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return document


@router.get("/{document_id}", response_model=DocumentOut, summary="Get one document")
async def get_document(document_id: str, user: CurrentUser):
    document = await _get_document_or_404(document_id, user)
    return DocumentOut.from_document(document)


@router.delete(
    "/{document_id}", response_model=Message, summary="Delete a document (admin only)"
)
async def delete_document(document_id: str, user: CurrentUser):
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete documents",
        )

    document = await _get_document_or_404(document_id, user)
    name = document.document_name
    stored = Path(document.file_path)

    # MongoDB has no foreign keys or ON DELETE CASCADE, so related documents
    # must be removed explicitly. This is a genuine cost of choosing Mongo here
    # and is called out in the README.
    await ParsedReport.find(ParsedReport.document_id == document_id).delete()
    await document.delete()

    try:
        stored.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete file from disk: %s", stored)

    await log_action(
        AuditAction.DOCUMENT_DELETED,
        user=user,
        document_name=name,
        remarks=f"Deleted '{name}'",
    )
    return Message(detail=f"Document '{name}' deleted")


@router.get("/{document_id}/download", summary="Download the original file")
async def download_document(document_id: str, user: CurrentUser):
    document = await _get_document_or_404(document_id, user)
    path = Path(document.file_path)

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="The stored file is no longer available",
        )

    # Confirm the resolved path is still inside the upload directory.
    if not str(path.resolve()).startswith(str(settings.UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return FileResponse(
        path, media_type=document.mime_type, filename=document.document_name
    )
