"""
Gemini integration: document classification and structured field extraction.

Design notes worth knowing:

  * The prompts are *generated from the parser specs*, not hard-coded. Change a
    FieldSpec and the prompt changes with it, so the two can never drift apart.

  * We ask for JSON via response_mime_type and then validate with our own code
    rather than trusting a schema constraint. Models still occasionally emit
    markdown fences or trailing prose, so the parsing is defensive.

  * Every call is retried with backoff. Free-tier rate limits are the single
    most common cause of failure in practice, and a bare exception there would
    lose the whole document.
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.models.enums import DocumentType
from app.parsers.base import DocumentSpec
from app.parsers.registry import classification_reference, get_spec
from app.services.ocr_service import prepare_image_for_vision

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
# Trim very long documents. Statements can run to hundreds of pages; the header
# and the first pages carry every summary field we need.
MAX_TEXT_CHARS = 30_000


class AIServiceError(Exception):
    """Raised when the model cannot be reached or returns unusable output."""


@dataclass
class ClassificationResult:
    document_type: DocumentType
    confidence: float
    reasoning: str


def _get_client():
    if not settings.GEMINI_API_KEY:
        raise AIServiceError(
            "GEMINI_API_KEY is not configured. Add it to your .env file - "
            "get a free key at https://aistudio.google.com/apikey"
        )
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise AIServiceError(
            "google-generativeai is not installed. Run: pip install -r requirements.txt"
        ) from exc

    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai


def _call_model(
    prompt: str,
    file_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    temperature: float = 0.1,
) -> str:
    """
    Send one request, retrying on transient failures.

    temperature is deliberately near zero: this is extraction, not creative
    writing. We want the same document to produce the same numbers every time.

    max_output_tokens is set generously because newer Gemini models spend
    output tokens on internal reasoning before emitting visible text. Setting
    it tight to "save quota" produces empty responses that look like API
    failures.
    """
    genai = _get_client()
    model = genai.GenerativeModel(settings.GEMINI_MODEL)

    parts: list[Any] = [prompt]
    if file_bytes and mime_type:
        parts.append({"mime_type": mime_type, "data": file_bytes})

    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = model.generate_content(
                parts,
                generation_config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                    "max_output_tokens": 8192,
                },
            )
            if not response.candidates:
                raise AIServiceError("Model returned no candidates (possibly filtered)")
            return response.text
        except Exception as exc:  # noqa: BLE001 - SDK raises many exception types
            last_error = exc
            message = str(exc).lower()
            is_transient = any(
                token in message
                for token in ("rate", "quota", "429", "503", "timeout", "deadline",
                              "unavailable", "internal")
            )
            if attempt < MAX_RETRIES and is_transient:
                delay = RETRY_BACKOFF ** attempt
                logger.warning(
                    "Gemini call failed (attempt %d/%d): %s - retrying in %.1fs",
                    attempt, MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
                continue
            break

    raise AIServiceError(f"Gemini request failed: {last_error}") from last_error


def _parse_json_response(text: str) -> dict[str, Any]:
    """
    Extract a JSON object from the model's reply.

    Even with response_mime_type set, output occasionally arrives wrapped in
    markdown fences or with a sentence in front. Rather than failing the whole
    document over formatting, we strip the common wrappers and, as a last
    resort, grab the outermost braces.
    """
    cleaned = text.strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        result = json.loads(cleaned)
        return result if isinstance(result, dict) else {"value": result}
    except json.JSONDecodeError:
        pass

    brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError as exc:
            raise AIServiceError(
                f"Model returned malformed JSON: {exc}. First 200 chars: {cleaned[:200]}"
            ) from exc

    raise AIServiceError(f"No JSON found in model response: {cleaned[:200]}")


# --- Classification -----------------------------------------------------

CLASSIFY_PROMPT = """You are a financial document classifier used by an Indian \
accounting firm.

Identify which ONE of these document types the content below represents:

{reference}

Rules:
- Choose exactly one type from the list, using the exact string in quotes.
- If the content matches none of them, or is too unclear to tell, return "unknown".
- Do not guess when the evidence is weak. A confident wrong answer is worse than \
an honest "unknown", because unknown routes the document to a human reviewer.
- Base the decision on the document's structure and headings, not on a single \
keyword appearing once.

Respond with JSON only:
{{
  "document_type": "<one of the exact strings above, or unknown>",
  "confidence": <number between 0 and 1>,
  "reasoning": "<one short sentence naming the specific evidence you used>"
}}

DOCUMENT CONTENT:
{content}
"""


def classify_document(
    text: str = "",
    file_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
) -> ClassificationResult:
    """Identify the document type. The user never picks this manually."""
    content = text[:8000] if text else "(see attached file)"
    prompt = CLASSIFY_PROMPT.format(
        reference=classification_reference(), content=content
    )

    raw = _call_model(prompt, file_bytes=file_bytes, mime_type=mime_type)
    parsed = _parse_json_response(raw)

    type_string = str(parsed.get("document_type", "unknown")).strip().lower()
    try:
        document_type = DocumentType(type_string)
    except ValueError:
        logger.warning("Classifier returned unrecognised type '%s'", type_string)
        document_type = DocumentType.UNKNOWN

    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    return ClassificationResult(
        document_type=document_type,
        confidence=confidence,
        reasoning=str(parsed.get("reasoning", ""))[:500],
    )


# --- Extraction ---------------------------------------------------------

EXTRACT_PROMPT = """You are extracting structured data from an Indian {label}.

Return JSON in exactly this shape:

{shape}

Rules:
- Use null for any field genuinely not present in the document. Never invent a \
plausible-looking value: a null tells the reviewer to look, a fabricated value \
does not.
- All amounts must be plain numbers. Strip currency symbols, commas and "/-". \
Write 45000 or 45000.50, not "Rs. 45,000/-".
- Amounts in brackets, like (1,200), are negative. Return -1200.
- All dates must be YYYY-MM-DD. Indian documents write dates day-first, so \
03/04/2024 means 3rd April 2024, not 4th March.
- Copy identifiers (PAN, GSTIN, IFSC, account numbers) character by character \
in upper case. Be careful with characters that look alike in scans: 0 vs O, \
1 vs I vs l, 5 vs S, 8 vs B, 2 vs Z.
- If an account number is printed masked, keep the mask exactly as shown.
- Numbers in Indian documents may use lakh grouping (1,20,000 = 120000).

Also include a "_confidence" key: a number from 0 to 1 for how reliably you \
could read this document. Lower it for blurry scans, cut-off text, or \
handwriting.

DOCUMENT CONTENT:
{content}
"""


def extract_fields(
    document_type: DocumentType,
    text: str = "",
    file_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
) -> tuple[dict[str, Any], float]:
    """Pull the spec's fields out of the document. Returns (data, confidence)."""
    spec: Optional[DocumentSpec] = get_spec(document_type)
    if spec is None:
        raise AIServiceError(f"No parser specification for '{document_type}'")

    content = text[:MAX_TEXT_CHARS] if text else "(see attached file)"
    prompt = EXTRACT_PROMPT.format(
        label=spec.label, shape=spec.json_shape(), content=content
    )

    raw = _call_model(prompt, file_bytes=file_bytes, mime_type=mime_type)
    data = _parse_json_response(raw)

    confidence = 0.5
    if "_confidence" in data:
        try:
            confidence = max(0.0, min(1.0, float(data.pop("_confidence"))))
        except (TypeError, ValueError):
            data.pop("_confidence", None)

    return data, confidence


def read_document_with_vision(file_path: str, mime_type: str) -> str:
    """
    Transcribe a scanned document. Used when there is no text layer.

    Kept separate from extraction so the raw text is stored for the reviewer to
    check against, and so a re-parse does not need a second OCR pass.
    """
    path = Path(file_path)
    file_bytes = (
        prepare_image_for_vision(path)
        if mime_type.startswith("image/")
        else path.read_bytes()
    )
    send_mime = "image/jpeg" if mime_type.startswith("image/") else mime_type

    prompt = """Transcribe every piece of text in this document, exactly as printed.

- Preserve the reading order and the table layout. Separate table columns with " | ".
- Include headers, footers, stamps and handwritten notes.
- Do not summarise, correct, reformat or interpret anything.
- If the page is rotated, read it in its correct orientation.

Return JSON: {"text": "<the full transcription>", "page_count": <number of pages>}
"""
    raw = _call_model(prompt, file_bytes=file_bytes, mime_type=send_mime, temperature=0.0)
    parsed = _parse_json_response(raw)
    transcription = str(parsed.get("text", "")).strip()

    if not transcription:
        raise AIServiceError(
            "OCR produced no text. The document may be blank or unreadable."
        )
    return transcription
