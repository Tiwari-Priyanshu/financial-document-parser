"""
Audit log endpoints.

    GET /api/logs
    GET /api/logs/document/{document_id}

The spec requires every action to be logged and viewable. These are read-only
by design - an audit trail that can be edited or deleted through the API is not
an audit trail.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.core.deps import CurrentUser
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, AuditStatus, UserRole
from app.schemas.common import PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["Audit Logs"])


class AuditLogOut(BaseModel):
    id: str
    action: AuditAction
    status: AuditStatus
    document_id: Optional[str]
    document_name: Optional[str]
    user_id: Optional[str]
    user_name: Optional[str]
    remarks: Optional[str]
    processing_time: Optional[float]
    created_at: datetime

    @classmethod
    def from_log(cls, log: AuditLog) -> "AuditLogOut":
        return cls(
            id=str(log.id),
            action=log.action,
            status=log.status,
            document_id=log.document_id,
            document_name=log.document_name,
            user_id=log.user_id,
            user_name=log.user_name,
            remarks=log.remarks,
            processing_time=log.processing_time,
            created_at=log.created_at,
        )


@router.get(
    "",
    response_model=PaginatedResponse[AuditLogOut],
    summary="List audit log entries with filters",
)
async def list_logs(
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[AuditAction] = None,
    log_status: Optional[AuditStatus] = Query(None, alias="status"),
    document_id: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    query: dict[str, Any] = {}

    # Analysts see only their own actions; admins see the whole trail.
    if user.role != UserRole.ADMIN:
        query["user_id"] = str(user.id)
    elif user_id:
        query["user_id"] = user_id

    if action:
        query["action"] = action.value
    if log_status:
        query["status"] = log_status.value
    if document_id:
        query["document_id"] = document_id

    if date_from or date_to:
        created: dict[str, datetime] = {}
        if date_from:
            created["$gte"] = date_from
        if date_to:
            created["$lte"] = date_to
        query["created_at"] = created

    total = await AuditLog.find(query).count()
    logs = (
        await AuditLog.find(query)
        .sort("-created_at")
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )

    return PaginatedResponse.create(
        items=[AuditLogOut.from_log(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/document/{document_id}",
    response_model=list[AuditLogOut],
    summary="Full processing timeline for one document",
)
async def document_timeline(document_id: str, user: CurrentUser):
    """
    Every stage a document went through, oldest first.

    This is what the frontend renders as a timeline on the document detail
    page - upload, OCR, classification, parsing, validation, review - each with
    its own duration.
    """
    query: dict[str, Any] = {"document_id": document_id}
    if user.role != UserRole.ADMIN:
        query["user_id"] = str(user.id)

    logs = await AuditLog.find(query).sort("+created_at").to_list()

    if not logs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No audit entries found for this document",
        )

    return [AuditLogOut.from_log(log) for log in logs]
