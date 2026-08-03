"""
Parsed result of a document.

Schema note (the thing to be able to defend in a review):

A pure-Mongo instinct says embed the parsed fields inside the Document itself -
one read, no join. We deliberately keep it in a separate collection because:

  1. A bank statement's transaction list can run to hundreds of entries plus
     the full raw OCR text. That is easily 100 KB+ per document.
  2. The document list endpoint is the most-hit route in the app and needs
     none of it - just name, type, status, size, timestamps.
  3. Embedding would force Mongo to pull those hundreds of KB into memory for
     every page of the list. Splitting keeps list queries small and fast, and
     the detail view pays for the second read only when it is actually opened.

This is the standard "extended reference" pattern: keep the hot, small fields
on the parent, push the cold, large payload into a child collection.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import pymongo
from beanie import Document as BeanieDocument
from pydantic import Field

from app.models.enums import ReviewStatus, ValidationStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParsedReport(BeanieDocument):
    document_id: str

    # Raw extracted text, kept so a reviewer can see where each value came from.
    raw_text: Optional[str] = None

    # The AI's structured output. Shape varies by document_type, which is
    # exactly the case Mongo handles better than a relational schema - no
    # 60-column table that is 85% NULL.
    parsed_data: dict[str, Any] = Field(default_factory=dict)

    # Manual corrections live separately so the original AI output is never
    # destroyed. That matters for measuring extraction accuracy later.
    corrected_data: Optional[dict[str, Any]] = None

    validation_status: ValidationStatus = ValidationStatus.PENDING
    # [{"field": "pan", "rule": "pan_format", "message": "...", "severity": "error"}]
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)

    review_status: ReviewStatus = ReviewStatus.PENDING
    reviewed_by: Optional[str] = None
    reviewer_name: Optional[str] = None
    remarks: Optional[str] = None

    confidence_score: Optional[float] = None      # 0.0 - 1.0
    extraction_method: Optional[str] = None       # "native_text" | "gemini_vision"

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "parsed_reports"
        indexes = [
            # One report per document, enforced by the database.
            pymongo.IndexModel([("document_id", pymongo.ASCENDING)], unique=True),
            pymongo.IndexModel([("review_status", pymongo.ASCENDING)]),
            pymongo.IndexModel([("validation_status", pymongo.ASCENDING)]),
            # Search by extracted values (PAN, GSTIN, invoice number, account
            # number, employee name, company name) without needing an index per
            # field. Wildcard indexes are a Mongo feature with no clean SQL
            # equivalent - a real argument in favour of this database here.
            pymongo.IndexModel([("parsed_data.$**", pymongo.ASCENDING)]),
        ]

    @property
    def effective_data(self) -> dict[str, Any]:
        """
        What exports and the dashboard should use: manual corrections win over
        raw AI output. The spec requires exports to always carry the latest
        approved data.
        """
        return self.corrected_data or self.parsed_data

    def __repr__(self) -> str:
        return f"<ParsedReport doc={self.document_id} review={self.review_status}>"