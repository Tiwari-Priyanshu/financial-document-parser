"""
Append-only audit trail.

Kept as its own collection because it grows without bound - one document can
easily generate 8-10 entries across its lifecycle. Embedding these in the
document would make every document read progressively heavier over time.
"""

from datetime import datetime, timezone
from typing import Optional

import pymongo
from beanie import Document as BeanieDocument
from pydantic import Field

from app.models.enums import AuditAction, AuditStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(BeanieDocument):
    # Optional because some actions (login, registration) have no document.
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None

    action: AuditAction
    status: AuditStatus = AuditStatus.SUCCESS
    remarks: Optional[str] = None
    processing_time: Optional[float] = None

    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "audit_logs"
        indexes = [
            pymongo.IndexModel([("document_id", pymongo.ASCENDING)]),
            pymongo.IndexModel([("user_id", pymongo.ASCENDING)]),
            pymongo.IndexModel([("action", pymongo.ASCENDING)]),
            pymongo.IndexModel([("created_at", pymongo.DESCENDING)]),
        ]

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} [{self.status}]>"