"""
File validation and storage helpers.

The core idea: never trust the filename or the Content-Type header the browser
sends. Both are attacker-controlled. We verify the actual bytes.
"""

import hashlib
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings


class FileValidationError(Exception):
    """Raised when an uploaded file fails a validation rule."""

    def __init__(self, message: str, code: str = "invalid_file"):
        self.message = message
        self.code = code
        super().__init__(message)


# Magic-byte signatures. Checking these means a renamed .exe cannot get through
# just because someone called it "invoice.pdf".
MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}

EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def detect_mime_type(content: bytes) -> Optional[str]:
    """Identify the file type from its leading bytes, or None if unrecognised."""
    for mime, signatures in MAGIC_SIGNATURES.items():
        if any(content.startswith(sig) for sig in signatures):
            return mime
    return None


def validate_upload(filename: str, content: bytes) -> str:
    """
    Run every upload rule from the spec. Returns the verified MIME type.
    Raises FileValidationError with a code the API layer turns into a useful
    message for the user.
    """
    if not filename:
        raise FileValidationError("File must have a name", "missing_filename")

    extension = Path(filename).suffix.lower()
    if extension not in settings.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(settings.ALLOWED_EXTENSIONS))
        raise FileValidationError(
            f"Unsupported file type '{extension}'. Allowed: {allowed}",
            "unsupported_extension",
        )

    if len(content) == 0:
        raise FileValidationError("File is empty", "empty_file")

    if len(content) > settings.max_upload_size_bytes:
        size_mb = len(content) / (1024 * 1024)
        raise FileValidationError(
            f"File is {size_mb:.1f} MB, maximum allowed is "
            f"{settings.MAX_UPLOAD_SIZE_MB} MB",
            "file_too_large",
        )

    actual_mime = detect_mime_type(content)
    if actual_mime is None:
        raise FileValidationError(
            "File contents are not a valid PDF, JPEG or PNG", "corrupted_file"
        )

    # Extension and real content must agree.
    expected_mime = EXTENSION_TO_MIME[extension]
    if actual_mime != expected_mime:
        raise FileValidationError(
            f"File extension says '{extension}' but the contents are {actual_mime}",
            "extension_mismatch",
        )

    if actual_mime == "application/pdf":
        _validate_pdf(content)

    return actual_mime


def _validate_pdf(content: bytes) -> None:
    """
    Catch password-protected and structurally broken PDFs at upload time rather
    than letting them blow up halfway through the parsing pipeline.
    """
    try:
        from io import BytesIO

        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        reader = PdfReader(BytesIO(content))

        if reader.is_encrypted:
            # Some PDFs are "encrypted" with an empty owner password and open
            # fine, so try that before rejecting.
            try:
                if reader.decrypt("") == 0:
                    raise FileValidationError(
                        "This PDF is password-protected. Please upload an "
                        "unlocked copy.",
                        "password_protected",
                    )
            except FileValidationError:
                raise
            except Exception:
                raise FileValidationError(
                    "This PDF is password-protected. Please upload an "
                    "unlocked copy.",
                    "password_protected",
                )

        if len(reader.pages) == 0:
            raise FileValidationError("PDF contains no pages", "blank_document")

    except FileValidationError:
        raise
    except PdfReadError as exc:
        raise FileValidationError(
            f"PDF appears to be corrupted and could not be read ({exc})",
            "corrupted_file",
        ) from exc
    except ImportError:
        return
    except Exception as exc:
        raise FileValidationError(
            f"Could not read this PDF: {exc}", "corrupted_file"
        ) from exc


def compute_file_hash(content: bytes) -> str:
    """SHA-256 of the raw bytes. Used for duplicate detection."""
    return hashlib.sha256(content).hexdigest()


def build_storage_path(original_filename: str) -> tuple[Path, str]:
    """
    Generate a collision-proof storage path.

    The stored name is a fresh UUID plus the extension - the user's filename is
    never used on disk. That removes path traversal ("../../etc/passwd"),
    overwrites between users, and problems with unicode or overlong names in
    one move. The original name is kept in the database for display.
    """
    extension = Path(original_filename).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{extension}"
    return settings.UPLOAD_DIR / stored_name, stored_name


def safe_display_name(filename: str) -> str:
    """Strip any directory components a client may have included."""
    return Path(filename).name[:255]
