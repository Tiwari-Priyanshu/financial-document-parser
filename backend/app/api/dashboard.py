"""
Dashboard analytics.

    GET /api/dashboard

Every figure is computed with MongoDB's aggregation framework rather than
pulling documents into Python and counting them there. On a few hundred
documents the difference is invisible; on a hundred thousand it is the
difference between a fast page and a timeout.

The whole dashboard is assembled with $facet, which runs every sub-pipeline in
a single round trip to the database instead of eight separate queries.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import ProcessingStatus, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Statuses that mean the pipeline finished and produced usable data.
SUCCESS_STATUSES = [
    ProcessingStatus.PARSED.value,
    ProcessingStatus.REVIEW_PENDING.value,
    ProcessingStatus.APPROVED.value,
]
FAILURE_STATUSES = [
    ProcessingStatus.VALIDATION_FAILED.value,
    ProcessingStatus.REJECTED.value,
]


class CountItem(BaseModel):
    label: str
    count: int


class TimeSeriesPoint(BaseModel):
    period: str
    count: int


class ActivityItem(BaseModel):
    action: str
    status: str
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    user_name: Optional[str] = None
    remarks: Optional[str] = None
    processing_time: Optional[float] = None
    created_at: datetime


class DashboardStats(BaseModel):
    total_documents: int
    successfully_parsed: int
    failed_parsing: int
    pending_review: int
    approved: int
    success_rate: float = Field(description="Percentage, 0-100")
    average_processing_time: float = Field(description="Seconds")
    documents_by_type: list[CountItem]
    documents_by_status: list[CountItem]
    daily_uploads: list[TimeSeriesPoint]
    monthly_uploads: list[TimeSeriesPoint]
    recent_activity: list[ActivityItem]


def _scope(user) -> dict[str, Any]:
    """Analysts only see their own numbers; admins see everything."""
    if user.role != UserRole.ADMIN:
        return {"uploaded_by": str(user.id)}
    return {}


@router.get("", response_model=DashboardStats, summary="Dashboard statistics")
async def get_dashboard(
    user: CurrentUser,
    days: int = Query(30, ge=1, le=365, description="Window for the daily chart"),
):
    match_stage = _scope(user)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # $facet runs each named sub-pipeline over the same matched set and returns
    # all results in one document - one database round trip for the whole page.
    pipeline: list[dict[str, Any]] = [
        {"$match": match_stage} if match_stage else {"$match": {}},
        {
            "$facet": {
                "totals": [{"$count": "value"}],
                "by_status": [
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "by_type": [
                    {"$match": {"document_type": {"$ne": None}}},
                    {"$group": {"_id": "$document_type", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "timing": [
                    {"$match": {"processing_time": {"$ne": None, "$gt": 0}}},
                    {
                        "$group": {
                            "_id": None,
                            "avg": {"$avg": "$processing_time"},
                            "count": {"$sum": 1},
                        }
                    },
                ],
                "daily": [
                    {"$match": {"created_at": {"$gte": since}}},
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": "%Y-%m-%d",
                                    "date": "$created_at",
                                }
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ],
                "monthly": [
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": "%Y-%m",
                                    "date": "$created_at",
                                }
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id": 1}},
                    {"$limit": 12},
                ],
            }
        },
    ]

    try:
        rows = await Document.aggregate(pipeline).to_list()
        facets = rows[0] if rows else {}
    except Exception:
        logger.exception("Dashboard aggregation failed")
        facets = {}

    def first_value(key: str, field: str, default: Any = 0) -> Any:
        bucket = facets.get(key) or []
        return bucket[0].get(field, default) if bucket else default

    total = first_value("totals", "value", 0)

    status_counts = {
        row["_id"]: row["count"] for row in (facets.get("by_status") or [])
    }
    parsed = sum(status_counts.get(s, 0) for s in SUCCESS_STATUSES)
    failed = sum(status_counts.get(s, 0) for s in FAILURE_STATUSES)

    # Only count documents that actually finished, so a queue of pending
    # uploads doesn't drag the success rate down and make it look broken.
    completed = parsed + failed
    success_rate = round((parsed / completed) * 100, 1) if completed else 0.0

    avg_time = round(float(first_value("timing", "avg", 0.0) or 0.0), 3)

    recent = (
        await AuditLog.find(
            {"user_id": str(user.id)} if user.role != UserRole.ADMIN else {}
        )
        .sort("-created_at")
        .limit(15)
        .to_list()
    )

    return DashboardStats(
        total_documents=total,
        successfully_parsed=parsed,
        failed_parsing=failed,
        pending_review=status_counts.get(ProcessingStatus.REVIEW_PENDING.value, 0),
        approved=status_counts.get(ProcessingStatus.APPROVED.value, 0),
        success_rate=success_rate,
        average_processing_time=avg_time,
        documents_by_type=[
            CountItem(label=row["_id"], count=row["count"])
            for row in (facets.get("by_type") or [])
        ],
        documents_by_status=[
            CountItem(label=row["_id"], count=row["count"])
            for row in (facets.get("by_status") or [])
        ],
        daily_uploads=[
            TimeSeriesPoint(period=row["_id"], count=row["count"])
            for row in (facets.get("daily") or [])
        ],
        monthly_uploads=[
            TimeSeriesPoint(period=row["_id"], count=row["count"])
            for row in (facets.get("monthly") or [])
        ],
        recent_activity=[
            ActivityItem(
                action=log.action.value,
                status=log.status.value,
                document_id=log.document_id,
                document_name=log.document_name,
                user_name=log.user_name,
                remarks=log.remarks,
                processing_time=log.processing_time,
                created_at=log.created_at,
            )
            for log in recent
        ],
    )
