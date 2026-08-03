"""Schemas for the document upload / listing endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import DocumentType, ProcessingStatus


class UploaderOut(BaseModel):
    """Trimmed user info nested inside document responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_name: str
    document_type: Optional[DocumentType]
    status: ProcessingStatus
    file_size: int
    mime_type: str
    processing_time: Optional[float]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    uploader: Optional[UploaderOut] = None

    @classmethod
    def from_document(cls, doc) -> "DocumentOut":
        """
        Build the API response from a Beanie document.

        Uploader details are denormalised onto the document at upload time, so
        listing 100 documents costs one query instead of one query plus 100
        user lookups. The tradeoff: if a user renames themselves, historical
        documents keep the old name. That is acceptable - arguably correct -
        for an audit-oriented system.
        """
        return cls(
            id=str(doc.id),
            document_name=doc.document_name,
            document_type=doc.document_type,
            status=doc.status,
            file_size=doc.file_size,
            mime_type=doc.mime_type,
            processing_time=doc.processing_time,
            error_message=doc.error_message,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            uploader=UploaderOut(
                id=doc.uploaded_by,
                name=doc.uploader_name,
                email=doc.uploader_email,
            ),
        )

    @computed_field
    @property
    def file_size_display(self) -> str:
        """Human-readable size so the frontend doesn't reimplement this."""
        size = float(self.file_size)
        for unit in ("B", "KB", "MB"):
            if size < 1024 or unit == "MB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} MB"


class UploadResponse(BaseModel):
    """
    Returned immediately after upload. Parsing runs in the background, so the
    client gets a processing_id to poll with rather than waiting for the AI.
    """

    document: DocumentOut
    processing_id: str = Field(
        description="Poll GET /api/parser/result/{processing_id} for progress"
    )
    message: str


class DuplicateDetail(BaseModel):
    """Body of the 409 returned when the same file is uploaded twice."""

    detail: str
    existing_document_id: str
    existing_document_name: str
    uploaded_at: datetime


class DocumentFilters(BaseModel):
    """Query parameters for the list endpoint, matching the spec's filter list."""

    document_type: Optional[DocumentType] = None
    status: Optional[ProcessingStatus] = None
    uploaded_by: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    min_processing_time: Optional[float] = None
    max_processing_time: Optional[float] = None
    search: Optional[str] = Field(
        default=None,
        description="Free-text search across filename and extracted fields "
                    "(PAN, GSTIN, invoice number, account number, names)",
    )
