"""
Parser endpoints.

    POST /api/parser/process/{document_id}
    POST /api/parser/reprocess/{document_id}
    GET  /api/parser/status/{document_id}
    GET  /api/parser/result/{document_id}
    PUT  /api/parser/result/{document_id}/fields     (manual corrections)
    POST /api/parser/result/{document_id}/approve
    POST /api/parser/result/{document_id}/reject
    GET  /api/parser/schema/{document_type}
"""

import logging
from typing import Any, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.models.document import Document
from app.models.enums import (
    AuditAction, DocumentType, ProcessingStatus, ReviewStatus,
    UserRole, ValidationStatus,
)
from app.models.report import ParsedReport, utcnow
from app.models.user import User
from app.parsers.registry import get_spec
from app.services import parser_service, validation_service
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/parser", tags=["Parser"])


# --- Schemas ------------------------------------------------------------


class FieldDefinition(BaseModel):
    """Sent to the frontend so the review form is generated, not hard-coded."""

    name: str
    label: str
    type: str
    mandatory: bool
    validator: Optional[str] = None


class ParseResult(BaseModel):
    document_id: str
    document_name: str
    document_type: Optional[DocumentType]
    status: ProcessingStatus
    validation_status: ValidationStatus
    validation_errors: list[dict[str, Any]]
    review_status: ReviewStatus
    parsed_data: dict[str, Any]
    corrected_data: Optional[dict[str, Any]]
    effective_data: dict[str, Any]
    confidence_score: Optional[float]
    extraction_method: Optional[str]
    processing_time: Optional[float]
    remarks: Optional[str]
    reviewed_by: Optional[str]
    reviewer_name: Optional[str]
    raw_text: Optional[str] = None
    field_definitions: list[FieldDefinition] = Field(default_factory=list)


class ProcessingStatusOut(BaseModel):
    """Lightweight body for the frontend's polling loop."""

    document_id: str
    status: ProcessingStatus
    document_type: Optional[DocumentType]
    processing_time: Optional[float]
    error_message: Optional[str]
    is_complete: bool


class FieldCorrections(BaseModel):
    corrections: dict[str, Any] = Field(
        description="Field name to corrected value. Only changed fields need sending."
    )
    remarks: Optional[str] = None


class ReviewDecision(BaseModel):
    remarks: Optional[str] = None


class ReprocessRequest(BaseModel):
    document_type: Optional[DocumentType] = Field(
        default=None,
        description="Force a specific type. Omit to re-run automatic classification.",
    )


# --- Helpers ------------------------------------------------------------


async def _get_accessible_document(document_id: str, user: User) -> Document:
    """
    Load a document the caller is allowed to see.

    Analysts only reach their own uploads. A missing document and someone
    else's document both return 404, never 403 - a 403 would confirm that the
    id exists, which leaks information to anyone enumerating ids.
    """
    try:
        object_id = PydanticObjectId(document_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    document = await Document.get(object_id)
    if document is None or (
        user.role != UserRole.ADMIN and document.uploaded_by != str(user.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return document


async def _get_report_or_404(document_id: str, message: str) -> ParsedReport:
    report = await ParsedReport.find_one(ParsedReport.document_id == document_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    return report


async def _run_pipeline_in_background(document_id: str, user: User) -> None:
    """
    Background tasks run after the response has been sent.

    Beanie holds a process-wide client initialised at startup, so unlike a
    session-per-request ORM there is nothing to open or close here - the task
    just awaits the pipeline.
    """
    await parser_service.process_document(document_id, user)


async def _run_reprocess_in_background(
    document_id: str, document_type: Optional[DocumentType], user: User
) -> None:
    if document_type:
        await parser_service.reprocess_with_type(document_id, document_type, user)
    else:
        await parser_service.process_document(document_id, user)


def _build_result(document: Document, report: ParsedReport) -> ParseResult:
    spec = get_spec(document.document_type) if document.document_type else None
    definitions = (
        [
            FieldDefinition(
                name=f.name, label=f.label, type=f.type.value,
                mandatory=f.mandatory, validator=f.validator,
            )
            for f in spec.fields
        ]
        if spec
        else []
    )
    return ParseResult(
        document_id=str(document.id),
        document_name=document.document_name,
        document_type=document.document_type,
        status=document.status,
        validation_status=report.validation_status,
        validation_errors=report.validation_errors,
        review_status=report.review_status,
        parsed_data=report.parsed_data or {},
        corrected_data=report.corrected_data,
        effective_data=report.effective_data or {},
        confidence_score=report.confidence_score,
        extraction_method=report.extraction_method,
        processing_time=document.processing_time,
        remarks=report.remarks,
        reviewed_by=report.reviewed_by,
        reviewer_name=report.reviewer_name,
        raw_text=report.raw_text,
        field_definitions=definitions,
    )


# --- Endpoints ----------------------------------------------------------


@router.post(
    "/process/{document_id}",
    response_model=ProcessingStatusOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start OCR, classification and parsing",
)
async def process(
    document_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
):
    """
    Queues the pipeline and returns 202 immediately.

    202 rather than 200 is deliberate: the work has been accepted but is not
    finished. The client polls GET /status/{id} until is_complete is true.
    """
    document = await _get_accessible_document(document_id, user)

    if document.status == ProcessingStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is already being processed",
        )

    document.status = ProcessingStatus.PROCESSING
    document.updated_at = utcnow()
    await document.save()

    background_tasks.add_task(_run_pipeline_in_background, str(document.id), user)

    return ProcessingStatusOut(
        document_id=str(document.id),
        status=document.status,
        document_type=document.document_type,
        processing_time=None,
        error_message=None,
        is_complete=False,
    )


@router.post(
    "/reprocess/{document_id}",
    response_model=ProcessingStatusOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run parsing, optionally forcing a document type",
)
async def reprocess(
    document_id: str,
    payload: ReprocessRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
):
    document = await _get_accessible_document(document_id, user)

    if document.status == ProcessingStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is already being processed",
        )

    document.status = ProcessingStatus.PROCESSING
    document.updated_at = utcnow()
    await document.save()

    background_tasks.add_task(
        _run_reprocess_in_background, str(document.id), payload.document_type, user
    )
    return ProcessingStatusOut(
        document_id=str(document.id),
        status=ProcessingStatus.PROCESSING,
        document_type=payload.document_type or document.document_type,
        processing_time=None,
        error_message=None,
        is_complete=False,
    )


@router.get(
    "/status/{document_id}",
    response_model=ProcessingStatusOut,
    summary="Cheap poll target for progress",
)
async def get_status(document_id: str, user: CurrentUser):
    document = await _get_accessible_document(document_id, user)
    return ProcessingStatusOut(
        document_id=str(document.id),
        status=document.status,
        document_type=document.document_type,
        processing_time=document.processing_time,
        error_message=document.error_message,
        is_complete=document.status
        not in (ProcessingStatus.UPLOADED, ProcessingStatus.PROCESSING),
    )


@router.get(
    "/result/{document_id}",
    response_model=ParseResult,
    summary="Full parse result with field definitions",
)
async def get_result(document_id: str, user: CurrentUser):
    document = await _get_accessible_document(document_id, user)
    report = await _get_report_or_404(
        document_id,
        "This document has not been parsed yet. "
        "POST /api/parser/process/{id} first.",
    )
    return _build_result(document, report)


@router.put(
    "/result/{document_id}/fields",
    response_model=ParseResult,
    summary="Save manual corrections to extracted values",
)
async def update_fields(
    document_id: str, payload: FieldCorrections, user: CurrentUser
):
    """
    Apply a reviewer's edits.

    Corrections are stored separately from parsed_data so the AI's original
    output is never destroyed. Every edit is re-validated, so fixing one field
    can clear an arithmetic warning on another.
    """
    document = await _get_accessible_document(document_id, user)
    report = await _get_report_or_404(document_id, "No parse result to edit")

    if document.document_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set the document type before editing fields",
        )

    merged = dict(report.effective_data)
    merged.update(payload.corrections)

    validation_status, issues, normalised = validation_service.validate_document(
        document.document_type, merged
    )

    report.corrected_data = normalised
    report.validation_status = validation_status
    report.validation_errors = issues
    if payload.remarks:
        report.remarks = payload.remarks
    report.updated_at = utcnow()
    await report.save()

    document.status = (
        ProcessingStatus.VALIDATION_FAILED
        if validation_status == ValidationStatus.FAILED
        else ProcessingStatus.REVIEW_PENDING
    )
    document.updated_at = utcnow()
    await document.save()

    await log_action(
        AuditAction.FIELDS_EDITED, user=user, document_id=document_id,
        document_name=document.document_name,
        remarks=f"Edited: {', '.join(sorted(payload.corrections))}"[:500],
    )
    return _build_result(document, report)


@router.post(
    "/result/{document_id}/approve",
    response_model=ParseResult,
    summary="Approve the extracted data",
)
async def approve(
    document_id: str, payload: ReviewDecision, user: CurrentUser
):
    document = await _get_accessible_document(document_id, user)
    report = await _get_report_or_404(document_id, "No parse result to approve")

    # Approving data with missing mandatory fields would let a broken record
    # flow into exports, which the spec explicitly forbids.
    if report.validation_status == ValidationStatus.FAILED:
        blocking = [
            issue["message"]
            for issue in report.validation_errors
            if issue.get("severity") == "error"
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Fix the blocking validation errors before approving",
                "code": "validation_failed",
                "errors": blocking,
            },
        )

    report.review_status = ReviewStatus.APPROVED
    report.reviewed_by = str(user.id)
    report.reviewer_name = user.name
    if payload.remarks:
        report.remarks = payload.remarks
    report.updated_at = utcnow()
    await report.save()

    document.status = ProcessingStatus.APPROVED
    document.updated_at = utcnow()
    await document.save()

    await log_action(
        AuditAction.DOCUMENT_APPROVED, user=user, document_id=document_id,
        document_name=document.document_name, remarks=payload.remarks,
    )
    return _build_result(document, report)


@router.post(
    "/result/{document_id}/reject",
    response_model=ParseResult,
    summary="Reject the parsing result",
)
async def reject(
    document_id: str, payload: ReviewDecision, user: CurrentUser
):
    document = await _get_accessible_document(document_id, user)
    report = await _get_report_or_404(document_id, "No parse result to reject")

    if not payload.remarks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reason is required when rejecting a parse",
        )

    report.review_status = ReviewStatus.REJECTED
    report.reviewed_by = str(user.id)
    report.reviewer_name = user.name
    report.remarks = payload.remarks
    report.updated_at = utcnow()
    await report.save()

    document.status = ProcessingStatus.REJECTED
    document.updated_at = utcnow()
    await document.save()

    await log_action(
        AuditAction.DOCUMENT_REJECTED, user=user, document_id=document_id,
        document_name=document.document_name, remarks=payload.remarks,
    )
    return _build_result(document, report)


@router.get(
    "/schema/{document_type}",
    response_model=list[FieldDefinition],
    summary="Field definitions for a document type",
)
async def get_schema(document_type: DocumentType, user: CurrentUser):
    """
    Lets the frontend build its review form dynamically. Adding a field to a
    parser spec makes it appear in the UI with no frontend change.
    """
    spec = get_spec(document_type)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No parser defined for '{document_type.value}'",
        )
    return [
        FieldDefinition(
            name=f.name, label=f.label, type=f.type.value,
            mandatory=f.mandatory, validator=f.validator,
        )
        for f in spec.fields
    ]
