"""
Report endpoints.

    GET /api/reports
    GET /api/reports/{document_id}
    GET /api/reports/export/pdf/{document_id}
    GET /api/reports/export/excel/{document_id}
    GET /api/reports/export/csv/{document_id}
"""

import logging
from datetime import datetime
from typing import Any, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.deps import CurrentUser
from app.models.document import Document
from app.models.enums import (
    AuditAction, DocumentType, ProcessingStatus, ReviewStatus,
    UserRole, ValidationStatus,
)
from app.models.report import ParsedReport
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.services import export_service
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["Reports"])

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}


class ReportSummary(BaseModel):
    document_id: str
    document_name: str
    document_type: Optional[DocumentType]
    status: ProcessingStatus
    validation_status: ValidationStatus
    review_status: ReviewStatus
    confidence_score: Optional[float]
    processing_time: Optional[float]
    field_count: int
    issue_count: int
    reviewer_name: Optional[str]
    uploader_name: str
    created_at: datetime


async def _document_and_report(
    document_id: str, user: User
) -> tuple[Document, ParsedReport]:
    """Load both, enforcing the same ownership rule as everywhere else."""
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

    report = await ParsedReport.find_one(ParsedReport.document_id == document_id)
    if report is None:
        # The spec is explicit: reports cannot be generated before parsing has
        # completed. 409 rather than 404 - the document exists, it just is not
        # in a state where a report is meaningful yet.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This document has not been parsed yet, so no report "
                           "can be generated",
                "code": "not_parsed",
                "current_status": document.status.value,
            },
        )
    return document, report


@router.get(
    "",
    response_model=PaginatedResponse[ReportSummary],
    summary="List parsed reports",
)
async def list_reports(
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_type: Optional[DocumentType] = None,
    review_status: Optional[ReviewStatus] = None,
    validation_status: Optional[ValidationStatus] = None,
):
    doc_query: dict[str, Any] = {}
    if user.role != UserRole.ADMIN:
        doc_query["uploaded_by"] = str(user.id)
    if document_type:
        doc_query["document_type"] = document_type.value

    documents = await Document.find(doc_query).sort("-created_at").to_list()
    doc_by_id = {str(d.id): d for d in documents}

    report_query: dict[str, Any] = {"document_id": {"$in": list(doc_by_id)}}
    if review_status:
        report_query["review_status"] = review_status.value
    if validation_status:
        report_query["validation_status"] = validation_status.value

    total = await ParsedReport.find(report_query).count()
    reports = (
        await ParsedReport.find(report_query)
        .sort("-created_at")
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )

    items = []
    for report in reports:
        document = doc_by_id.get(report.document_id)
        if document is None:
            continue
        items.append(ReportSummary(
            document_id=report.document_id,
            document_name=document.document_name,
            document_type=document.document_type,
            status=document.status,
            validation_status=report.validation_status,
            review_status=report.review_status,
            confidence_score=report.confidence_score,
            processing_time=document.processing_time,
            field_count=len([
                v for v in (report.effective_data or {}).values()
                if v not in (None, "", [])
            ]),
            issue_count=len(report.validation_errors or []),
            reviewer_name=report.reviewer_name,
            uploader_name=document.uploader_name,
            created_at=report.created_at,
        ))

    return PaginatedResponse.create(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get(
    "/{document_id}", response_model=ReportSummary, summary="One report's summary"
)
async def get_report(document_id: str, user: CurrentUser):
    document, report = await _document_and_report(document_id, user)
    return ReportSummary(
        document_id=document_id,
        document_name=document.document_name,
        document_type=document.document_type,
        status=document.status,
        validation_status=report.validation_status,
        review_status=report.review_status,
        confidence_score=report.confidence_score,
        processing_time=document.processing_time,
        field_count=len([
            v for v in (report.effective_data or {}).values()
            if v not in (None, "", [])
        ]),
        issue_count=len(report.validation_errors or []),
        reviewer_name=report.reviewer_name,
        uploader_name=document.uploader_name,
        created_at=report.created_at,
    )


async def _export(document_id: str, user: User, fmt: str) -> StreamingResponse:
    """Shared body for all three export endpoints."""
    import io

    document, report = await _document_and_report(document_id, user)

    generators = {
        "pdf": export_service.generate_pdf,
        "xlsx": export_service.generate_excel,
        "csv": export_service.generate_csv,
    }

    try:
        payload = generators[fmt](document, report)
    except export_service.ExportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    filename = export_service.safe_filename(document, fmt)

    await log_action(
        AuditAction.REPORT_GENERATED,
        user=user,
        document_id=document_id,
        document_name=document.document_name,
        remarks=f"Exported as {fmt.upper()} ({len(payload)} bytes)",
    )

    return StreamingResponse(
        io.BytesIO(payload),
        media_type=MEDIA_TYPES[fmt],
        headers={
            # attachment triggers a download rather than rendering in the tab
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
        },
    )


@router.get("/export/pdf/{document_id}", summary="Download the report as PDF")
async def export_pdf(document_id: str, user: CurrentUser):
    return await _export(document_id, user, "pdf")


@router.get("/export/excel/{document_id}", summary="Download the report as Excel")
async def export_excel(document_id: str, user: CurrentUser):
    return await _export(document_id, user, "xlsx")


@router.get("/export/csv/{document_id}", summary="Download the report as CSV")
async def export_csv(document_id: str, user: CurrentUser):
    return await _export(document_id, user, "csv")
