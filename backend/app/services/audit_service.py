"""
Audit logging.

The spec requires every action to be logged. Funnelling it through one helper
keeps entries consistent and call sites readable.
"""

import logging
from typing import Optional

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, AuditStatus
from app.models.user import User

logger = logging.getLogger(__name__)


async def log_action(
    action: AuditAction,
    *,
    status: AuditStatus = AuditStatus.SUCCESS,
    user: Optional[User] = None,
    document_id: Optional[str] = None,
    document_name: Optional[str] = None,
    remarks: Optional[str] = None,
    processing_time: Optional[float] = None,
) -> Optional[AuditLog]:
    """
    Write one audit entry.

    Auditing must never be the reason a request fails, so errors here are
    logged and swallowed. A missing audit row is bad; a 500 on an otherwise
    successful upload because the audit insert failed is worse.
    """
    try:
        entry = AuditLog(
            action=action,
            status=status,
            user_id=str(user.id) if user else None,
            user_name=user.name if user else None,
            document_id=document_id,
            document_name=document_name,
            remarks=remarks,
            processing_time=processing_time,
        )
        await entry.insert()
        return entry
    except Exception:
        logger.exception("Failed to write audit log for action=%s", action)
        return None
