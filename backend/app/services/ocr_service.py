"""
Text extraction from uploaded files.

Strategy - the main engineering decision in the whole pipeline:

Most Indian financial documents that arrive as PDFs are *digitally generated*,
not scanned. Bank statements from net banking, GST returns downloaded from the
portal, ITR acknowledgements, invoices from Tally - all carry a real text layer.
Running those through a vision model is slow, costs an API call, and is *less*
accurate than simply reading the text that is already there.

So we try the cheap path first:

    PDF with a usable text layer  ->  pdfplumber        (~50ms, free, exact)
    Scanned PDF / image           ->  Gemini vision     (~5s, API call)

On a realistic mix of documents this keeps the majority of uploads off the API
entirely, which matters a great deal on a free tier with rate limits.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Raised when no text could be recovered from a document."""


@dataclass
class ExtractionResult:
    text: str
    method: str            # "native_text" | "gemini_vision"
    page_count: int
    duration: float
    needs_vision: bool = False   # True when the caller must fall back to the model


def extract_text(file_path: str, mime_type: str) -> ExtractionResult:
    """
    Pull text out of the file using the cheapest method that works.

    For images, and for PDFs with no usable text layer, returns a result with
    needs_vision=True and empty text - the AI service handles those by sending
    the file itself to the model.
    """
    start = time.perf_counter()
    path = Path(file_path)

    if not path.exists():
        raise OCRError(f"File not found on disk: {file_path}")

    if mime_type == "application/pdf":
        text, page_count = _extract_pdf_text(path)
        duration = time.perf_counter() - start

        if len(text.strip()) >= settings.NATIVE_TEXT_THRESHOLD:
            logger.info(
                "Native text layer used: %d chars from %d pages in %.3fs",
                len(text), page_count, duration,
            )
            return ExtractionResult(
                text=text, method="native_text",
                page_count=page_count, duration=duration,
            )

        # Text layer missing or too thin - this is a scanned PDF.
        logger.info(
            "Only %d chars of native text found, falling back to vision OCR",
            len(text.strip()),
        )
        return ExtractionResult(
            text="", method="gemini_vision", page_count=page_count,
            duration=duration, needs_vision=True,
        )

    # Images always need the vision model.
    return ExtractionResult(
        text="", method="gemini_vision", page_count=1,
        duration=time.perf_counter() - start, needs_vision=True,
    )


def _extract_pdf_text(path: Path) -> tuple[str, int]:
    """
    Read every page's text layer, preserving table structure where possible.

    pdfplumber is used rather than pypdf because it keeps column positions,
    which matters enormously for bank statement tables - pypdf tends to
    interleave columns into unreadable soup.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise OCRError("pdfplumber is not installed") from exc

    chunks: list[str] = []
    page_count = 0

    try:
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for index, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text(layout=True) or ""

                # Pull tables out separately and render them as pipe-delimited
                # rows. Without this, transaction tables lose their row
                # boundaries and the model has to guess where one ends.
                tables = page.extract_tables() or []
                table_text = ""
                for table in tables:
                    rows = [
                        " | ".join((cell or "").strip() for cell in row)
                        for row in table
                        if any(cell for cell in row)
                    ]
                    if rows:
                        table_text += "\n[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]\n"

                if page_text.strip() or table_text.strip():
                    chunks.append(
                        f"--- Page {index} of {page_count} ---\n"
                        f"{page_text}\n{table_text}"
                    )
    except Exception as exc:
        logger.warning("pdfplumber failed on %s: %s", path.name, exc)
        return "", page_count

    return "\n\n".join(chunks), page_count


def prepare_image_for_vision(path: Path) -> bytes:
    """
    Normalise an image before sending it to the model.

    Two adjustments that measurably improve extraction on phone photos of
    documents, which is what users actually upload:

      - EXIF rotation is applied. Phones store photos in landscape and record
        the intended rotation as metadata; a model reading the raw pixels sees
        a sideways document.
      - Very large images are downscaled. Beyond roughly 2000px on the long
        edge there is no accuracy gain, only a bigger payload and slower call.
    """
    try:
        from io import BytesIO

        from PIL import Image, ImageOps

        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)   # honour EXIF orientation
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            max_edge = 2000
            if max(img.size) > max_edge:
                ratio = max_edge / max(img.size)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=90)
            return buffer.getvalue()
    except ImportError:
        logger.warning("Pillow not available, sending image unprocessed")
        return path.read_bytes()
    except Exception as exc:
        logger.warning("Image preprocessing failed (%s), sending original", exc)
        return path.read_bytes()


def get_page_count(file_path: str, mime_type: str) -> int:
    if mime_type != "application/pdf":
        return 1
    try:
        from pypdf import PdfReader

        return len(PdfReader(file_path).pages)
    except Exception:
        return 1
