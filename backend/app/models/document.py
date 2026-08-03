"""Uploaded document collection."""

from datetime import datetime, timezone
from typing import Optional

import pymongo
from beanie import Document as BeanieDocument
from pydantic import Field

from app.models.enums import DocumentType, ProcessingStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(BeanieDocument):
    document_name: str
    # None until the AI classifier has run - the user never picks this manually.
    document_type: Optional[DocumentType] = None

    file_path: str
    file_size: int          # bytes
    mime_type: str

    # SHA-256 of the file contents. This is how duplicate uploads are detected;
    # comparing filenames would be useless since users rename files constantly.
    file_hash: str

    uploaded_by: str        # User id as a string
    uploader_name: str      # Denormalised - see note below
    uploader_email: str

    status: ProcessingStatus = ProcessingStatus.UPLOADED
    processing_time: Optional[float] = None   # seconds
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "documents"
        indexes = [
            pymongo.IndexModel([("uploaded_by", pymongo.ASCENDING)]),
            pymongo.IndexModel([("status", pymongo.ASCENDING)]),
            pymongo.IndexModel([("document_type", pymongo.ASCENDING)]),
            # Duplicate detection is scoped per user, so the lookup always
            # filters on both fields. A compound index serves it in one seek.
            pymongo.IndexModel([
                ("uploaded_by", pymongo.ASCENDING),
                ("file_hash", pymongo.ASCENDING),
            ]),
            # The document list is always sorted newest-first and usually
            # filtered by status, so this compound index covers the hot path.
            pymongo.IndexModel([
                ("status", pymongo.ASCENDING),
                ("created_at", pymongo.DESCENDING),
            ]),
            pymongo.IndexModel([("created_at", pymongo.DESCENDING)]),
            # Text index powers filename search.
            pymongo.IndexModel([("document_name", pymongo.TEXT)]),
        ]

    def __repr__(self) -> str:
        return f"<Document {self.document_name} [{self.status}]>"