"""
The processing pipeline.

    upload -> OCR -> classify -> extract -> validate -> route for review

Every stage writes an audit entry and updates the document's status, so the
frontend can poll and show real progress rather than an indefinite spinner.

The whole thing is wrapped so that *any* failure still leaves the document in a
sane, resumable state. A document that dies during extraction must not sit on
"processing" forever - it lands in REVIEW_PENDING with the error recorded, and
the user can hit reprocess.

Note on blocking calls: pdfplumber and the Gemini SDK are both synchronous and
CPU/network bound. Calling them directly inside an async function would block
the event loop and stall every other request for the duration. They are pushed
onto a worker thread with asyncio.to_thread instead.
"""

import asyncio
import logging
import time
from typing import Optional

from app.models.document import Document
from app.models.enums import (
    AuditAction, AuditStatus, DocumentType, ProcessingStatus,
    ReviewStatus, ValidationStatus,
)
from app.models.report import ParsedReport, utcnow
from app.models.user import User
from app.services import ai_service, ocr_service, validation_service
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

# Below this the classifier is not trusted, and the document goes to a human
# rather than being extracted against a type that is probably wrong.
CLASSIFICATION_CONFIDENCE_FLOOR = 0.55


async def process_document(document_id: str, user: Optional[User] = None) -> None:
    """
    Run the full pipeline for one document.

    Called from a background task, so it must never let an exception escape -
    an unhandled error in a background task vanishes silently and the user is
    left staring at a document stuck on "processing".
    """
    document = await _load(document_id)
    if document is None:
        logger.error("process_document called for missing document %s", document_id)
        return

    pipeline_start = time.perf_counter()
    document.status = ProcessingStatus.PROCESSING
    document.error_message = None
    document.updated_at = utcnow()
    await document.save()

    try:
        raw_text, method = await _run_ocr(document)
        document_type = await _run_classification(document, raw_text)

        if document_type == DocumentType.UNKNOWN:
            await _finish_as_unknown(document, raw_text, method, pipeline_start)
            return

        await _run_extraction_and_validation(
            document, document_type, raw_text, method, pipeline_start
        )

    except Exception as exc:  # noqa: BLE001 - background task must never crash
        logger.exception("Pipeline failed for document %s", document_id)
        await _finish_as_failed(document_id, exc, pipeline_start)


# --- Stages -------------------------------------------------------------


async def _run_ocr(document: Document) -> tuple[str, str]:
    """Get the document's text, cheapest route first."""
    await log_action(
        AuditAction.OCR_STARTED,
        document_id=str(document.id),
        document_name=document.document_name,
    )
    start = time.perf_counter()

    result = await asyncio.to_thread(
        ocr_service.extract_text, document.file_path, document.mime_type
    )

    if result.needs_vision:
        # No usable text layer: this is a scan or a phone photo.
        raw_text = await asyncio.to_thread(
            ai_service.read_document_with_vision,
            document.file_path,
            document.mime_type,
        )
        method = "gemini_vision"
    else:
        raw_text = result.text
        method = "native_text"

    duration = time.perf_counter() - start

    if not raw_text.strip():
        raise ai_service.AIServiceError(
            "No text could be extracted. The document may be blank or the scan "
            "quality too low."
        )

    await log_action(
        AuditAction.OCR_COMPLETED,
        document_id=str(document.id),
        document_name=document.document_name,
        remarks=f"{method}: {len(raw_text)} characters from {result.page_count} page(s)",
        processing_time=round(duration, 3),
    )
    return raw_text, method


async def _run_classification(document: Document, raw_text: str) -> DocumentType:
    start = time.perf_counter()
    result = await asyncio.to_thread(ai_service.classify_document, raw_text)

    # A low-confidence guess is treated as no answer at all.
    if result.confidence < CLASSIFICATION_CONFIDENCE_FLOOR:
        logger.info(
            "Classification confidence %.2f below floor for %s - routing to review",
            result.confidence, document.id,
        )
        document_type = DocumentType.UNKNOWN
    else:
        document_type = result.document_type

    document.document_type = document_type
    document.updated_at = utcnow()
    await document.save()

    await log_action(
        AuditAction.CLASSIFICATION_COMPLETED,
        document_id=str(document.id),
        document_name=document.document_name,
        remarks=(
            f"Identified as '{document_type.value}' "
            f"(confidence {result.confidence:.2f}): {result.reasoning}"
        ),
        processing_time=round(time.perf_counter() - start, 3),
    )
    return document_type


async def _run_extraction_and_validation(
    document: Document,
    document_type: DocumentType,
    raw_text: str,
    method: str,
    pipeline_start: float,
) -> None:
    await log_action(
        AuditAction.PARSING_STARTED,
        document_id=str(document.id),
        document_name=document.document_name,
    )
    start = time.perf_counter()

    data, model_confidence = await asyncio.to_thread(
        ai_service.extract_fields, document_type, raw_text
    )

    await log_action(
        AuditAction.PARSING_COMPLETED,
        document_id=str(document.id),
        document_name=document.document_name,
        remarks=f"{len(data)} fields returned",
        processing_time=round(time.perf_counter() - start, 3),
    )

    validation_status, issues, normalised = validation_service.validate_document(
        document_type, data
    )
    completeness = validation_service.completeness_score(document_type, normalised)

    # Blend what the model claims with what we can actually observe. A model can
    # report 0.95 confidence while leaving half the fields empty; completeness
    # keeps that honest.
    confidence = round((model_confidence * 0.6) + (completeness * 0.4), 3)

    report = await _upsert_report(str(document.id))
    report.raw_text = raw_text[:100_000]
    report.parsed_data = normalised
    report.validation_status = validation_status
    report.validation_errors = issues
    report.confidence_score = confidence
    report.extraction_method = method
    report.review_status = ReviewStatus.PENDING
    report.updated_at = utcnow()
    await report.save()

    if validation_status == ValidationStatus.FAILED:
        document.status = ProcessingStatus.VALIDATION_FAILED
        await log_action(
            AuditAction.VALIDATION_FAILED,
            status=AuditStatus.FAILURE,
            document_id=str(document.id),
            document_name=document.document_name,
            remarks="; ".join(i["message"] for i in issues[:5]),
        )
    else:
        document.status = ProcessingStatus.REVIEW_PENDING
        await log_action(
            AuditAction.VALIDATION_PASSED,
            document_id=str(document.id),
            document_name=document.document_name,
            remarks=(
                f"{validation_status.value}, confidence {confidence:.2f}, "
                f"{len(issues)} issue(s)"
            ),
        )

    document.processing_time = round(time.perf_counter() - pipeline_start, 3)
    document.updated_at = utcnow()
    await document.save()


async def _finish_as_unknown(
    document: Document, raw_text: str, method: str, pipeline_start: float
) -> None:
    """Store what we have and let a human decide the type."""
    report = await _upsert_report(str(document.id))
    report.raw_text = raw_text[:100_000]
    report.parsed_data = {}
    report.validation_status = ValidationStatus.FAILED
    report.validation_errors = [{
        "field": "document_type",
        "rule": "unrecognised_document",
        "message": (
            "This document could not be confidently matched to any supported "
            "type. Set the type manually to parse it."
        ),
        "severity": "error",
    }]
    report.review_status = ReviewStatus.PENDING
    report.extraction_method = method
    report.confidence_score = 0.0
    report.updated_at = utcnow()
    await report.save()

    document.status = ProcessingStatus.REVIEW_PENDING
    document.processing_time = round(time.perf_counter() - pipeline_start, 3)
    document.updated_at = utcnow()
    await document.save()

    await log_action(
        AuditAction.MANUAL_REVIEW,
        status=AuditStatus.INFO,
        document_id=str(document.id),
        document_name=document.document_name,
        remarks="Document type could not be determined - awaiting manual classification",
    )


async def _finish_as_failed(
    document_id: str, exc: Exception, pipeline_start: float
) -> None:
    document = await _load(document_id)
    if document is None:
        return

    document.status = ProcessingStatus.REVIEW_PENDING
    document.error_message = str(exc)[:1000]
    document.processing_time = round(time.perf_counter() - pipeline_start, 3)
    document.updated_at = utcnow()
    await document.save()

    await log_action(
        AuditAction.PARSING_FAILED,
        status=AuditStatus.FAILURE,
        document_id=document_id,
        document_name=document.document_name,
        remarks=str(exc)[:500],
        processing_time=document.processing_time,
    )


# --- Helpers ------------------------------------------------------------


async def _load(document_id: str) -> Optional[Document]:
    from beanie import PydanticObjectId

    try:
        return await Document.get(PydanticObjectId(document_id))
    except Exception:
        return None


async def _upsert_report(document_id: str) -> ParsedReport:
    """Reuse the existing report on reprocess rather than piling up duplicates."""
    report = await ParsedReport.find_one(ParsedReport.document_id == document_id)
    if report is None:
        report = ParsedReport(document_id=document_id)
        await report.insert()
    return report


async def reprocess_with_type(
    document_id: str, document_type: DocumentType, user: Optional[User] = None
) -> None:
    """
    Re-run extraction against a type the reviewer chose by hand.

    Skips OCR entirely when raw text is already stored - one API call instead of
    two, and noticeably faster.
    """
    document = await _load(document_id)
    if document is None:
        return

    report = await _upsert_report(document_id)
    raw_text = report.raw_text or ""

    pipeline_start = time.perf_counter()
    document.status = ProcessingStatus.PROCESSING
    document.document_type = document_type
    document.updated_at = utcnow()
    await document.save()

    await log_action(
        AuditAction.REPROCESS_REQUESTED,
        user=user,
        document_id=document_id,
        document_name=document.document_name,
        remarks=f"Manual type override: {document_type.value}",
    )

    try:
        if not raw_text:
            raw_text, method = await _run_ocr(document)
        else:
            method = report.extraction_method or "native_text"

        await _run_extraction_and_validation(
            document, document_type, raw_text, method, pipeline_start
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Reprocess failed for %s", document_id)
        await _finish_as_failed(document_id, exc, pipeline_start)
