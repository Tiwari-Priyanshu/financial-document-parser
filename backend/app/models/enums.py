"""
Enums shared across models, schemas and services.

These are plain str-Enums, so they serialise straight to JSON and store as
plain strings in MongoDB. Adding a new value is a code change only - no
migration, no schema alteration.
"""

from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"


class DocumentType(str, Enum):
    BANK_STATEMENT = "bank_statement"
    ITR = "itr"
    GST_RETURN = "gst_return"
    SALARY_SLIP = "salary_slip"
    INVOICE = "invoice"
    BALANCE_SHEET = "balance_sheet"
    PROFIT_LOSS = "profit_loss"
    # Bonus types from the spec
    CREDIT_CARD_STATEMENT = "credit_card_statement"
    FORM_16 = "form_16"
    EPF_STATEMENT = "epf_statement"
    # Fallback when the classifier is not confident
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PARSED = "parsed"
    VALIDATION_FAILED = "validation_failed"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"   # some non-mandatory fields failed their format check


class ReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AuditAction(str, Enum):
    USER_REGISTERED = "user_registered"
    USER_LOGIN = "user_login"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_DELETED = "document_deleted"
    OCR_STARTED = "ocr_started"
    OCR_COMPLETED = "ocr_completed"
    OCR_FAILED = "ocr_failed"
    CLASSIFICATION_COMPLETED = "classification_completed"
    PARSING_STARTED = "parsing_started"
    PARSING_COMPLETED = "parsing_completed"
    PARSING_FAILED = "parsing_failed"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    MANUAL_REVIEW = "manual_review"
    FIELDS_EDITED = "fields_edited"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REJECTED = "document_rejected"
    REPROCESS_REQUESTED = "reprocess_requested"
    REPORT_GENERATED = "report_generated"


class AuditStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INFO = "info"