"""
Validation engine.

Two layers of checking:

  1. Format validation - does the PAN look like a PAN, is the GSTIN checksum
     right, is the IFSC well-formed. Catches OCR misreads such as O/0 and I/1.

  2. Cross-field validation - do the numbers agree with each other. An invoice
     where subtotal + tax does not reach the printed total means something was
     read wrong, even though every individual field looks fine.

The second layer is what makes this a financial parser rather than a generic
text extractor.
"""

import re
from datetime import date, datetime
from typing import Any, Optional

from app.models.enums import DocumentType, ValidationStatus
from app.parsers.base import DocumentSpec, FieldType
from app.parsers.registry import get_spec

# --- Format patterns ----------------------------------------------------

PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCOUNT_PATTERN = re.compile(r"^[0-9Xx*]{6,20}$")

# 4th character of a PAN encodes the type of holder.
PAN_ENTITY_CODES = {
    "P": "Individual", "C": "Company", "H": "Hindu Undivided Family",
    "F": "Firm", "A": "Association of Persons", "T": "Trust",
    "B": "Body of Individuals", "L": "Local Authority",
    "J": "Artificial Juridical Person", "G": "Government",
}

# First two digits of a GSTIN are the state code.
VALID_GST_STATE_CODES = {f"{i:02d}" for i in range(1, 39)} | {"97", "99"}

GSTIN_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class FieldIssue(dict):
    """A single validation problem, shaped for JSON storage and the UI."""

    def __init__(self, field: str, rule: str, message: str, severity: str = "error"):
        super().__init__(field=field, rule=rule, message=message, severity=severity)


# --- Format validators --------------------------------------------------


def validate_pan(value: str) -> Optional[str]:
    """Returns an error message, or None if valid."""
    v = str(value).strip().upper().replace(" ", "")
    if not PAN_PATTERN.match(v):
        return (
            "PAN must be 5 letters, 4 digits, then 1 letter (e.g. ABCPE1234F). "
            f"Got '{value}'"
        )
    if v[3] not in PAN_ENTITY_CODES:
        return (
            f"'{v[3]}' is not a valid PAN holder-type code in position 4 "
            f"(expected one of {', '.join(sorted(PAN_ENTITY_CODES))})"
        )
    return None


def gstin_checksum(gstin: str) -> Optional[str]:
    """
    Compute the expected 15th character of a GSTIN.

    GSTIN carries a mod-36 check digit. Verifying it catches transposed or
    misread characters that a regex alone would happily accept - which is
    exactly the failure mode of OCR on a low-quality scan.
    """
    if len(gstin) != 15:
        return None
    total = 0
    for i, char in enumerate(gstin[:14]):
        if char not in GSTIN_CHARSET:
            return None
        value = GSTIN_CHARSET.index(char)
        factor = 2 if i % 2 else 1
        product = value * factor
        total += product // 36 + product % 36
    return GSTIN_CHARSET[(36 - total % 36) % 36]


def validate_gstin(value: str) -> Optional[str]:
    v = str(value).strip().upper().replace(" ", "")
    if not GSTIN_PATTERN.match(v):
        return (
            "GSTIN must be 15 characters: 2-digit state code, 10-character PAN, "
            f"entity digit, 'Z', then a check digit. Got '{value}'"
        )
    if v[:2] not in VALID_GST_STATE_CODES:
        return f"'{v[:2]}' is not a valid GST state code"

    pan_part = v[2:12]
    if not PAN_PATTERN.match(pan_part):
        return f"The PAN embedded in this GSTIN is malformed: '{pan_part}'"

    expected = gstin_checksum(v)
    if expected and v[14] != expected:
        return (
            f"GSTIN checksum failed - last character should be '{expected}' "
            f"but is '{v[14]}'. The number was likely misread."
        )
    return None


def validate_ifsc(value: str) -> Optional[str]:
    v = str(value).strip().upper().replace(" ", "")
    if not IFSC_PATTERN.match(v):
        return (
            "IFSC must be 4 letters, then '0', then 6 alphanumeric characters "
            f"(e.g. HDFC0000123). Got '{value}'"
        )
    return None


def validate_account_number(value: str) -> Optional[str]:
    v = str(value).strip().replace(" ", "").replace("-", "")
    if not ACCOUNT_PATTERN.match(v):
        return (
            "Account number should be 6-20 digits, optionally masked with X. "
            f"Got '{value}'"
        )
    return None


DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
    "%Y/%m/%d", "%d-%b-%Y", "%d %B %Y", "%b %d, %Y",
)


def parse_flexible_date(value: str) -> Optional[date]:
    """
    Accept the many date formats Indian financial documents use.

    Note the ordering: day-first formats come before month-first ones, because
    dd/mm/yyyy is the Indian convention. Getting this backwards silently turns
    03/04/2024 from 3rd April into 4th March.
    """
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def validate_date(value: str) -> Optional[str]:
    parsed = parse_flexible_date(value)
    if parsed is None:
        return f"Could not read '{value}' as a date"
    if parsed.year < 1900 or parsed > date.today():
        return f"Date '{value}' is outside a plausible range"
    return None


FORMAT_VALIDATORS = {
    "pan": validate_pan,
    "gstin": validate_gstin,
    "ifsc": validate_ifsc,
    "account_number": validate_account_number,
    "date": validate_date,
}


# --- Value coercion -----------------------------------------------------

# Currency words, including any trailing full stop ("Rs." must go entirely -
# leaving the dot behind turns "Rs. 45,000" into the number 0.45).
CURRENCY_WORDS = re.compile(r"(?i)\b(?:rs|inr|usd|rupees|eur|gbp)\b\.?")
CURRENCY_NOISE = re.compile(r"[₹$€£,\s]")


def coerce_number(value: Any) -> Optional[float]:
    """
    Turn whatever the model returned into a float.

    Models return "Rs. 45,000/-", "(1,200)" for negatives, and "1,20,000" in the
    Indian lakh grouping. All of these should become numbers rather than being
    flagged as invalid.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    # Accounting notation: parentheses mean negative.
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")

    text = CURRENCY_WORDS.sub("", text)
    text = CURRENCY_NOISE.sub("", text)
    text = text.replace("/-", "").replace("-/", "")

    # Any dot left at the very start came from a stripped currency word, not
    # from a decimal point.
    text = text.lstrip(".").rstrip(".")

    if text.startswith("-"):
        negative = True
        text = text[1:]

    if not text:
        return None

    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def normalise_parsed_data(data: dict[str, Any], spec: DocumentSpec) -> dict[str, Any]:
    """Clean the model's raw output into consistent types before validating."""
    cleaned: dict[str, Any] = {}
    for field in spec.fields:
        raw = data.get(field.name)
        if raw is None or raw == "" or (isinstance(raw, str) and raw.lower() in
                                        {"n/a", "na", "null", "none", "not found", "-"}):
            cleaned[field.name] = None
            continue

        if field.type == FieldType.NUMBER:
            cleaned[field.name] = coerce_number(raw)
        elif field.type == FieldType.DATE:
            parsed = parse_flexible_date(raw)
            cleaned[field.name] = parsed.isoformat() if parsed else str(raw).strip()
        elif field.type == FieldType.ARRAY:
            cleaned[field.name] = raw if isinstance(raw, list) else []
        else:
            text = str(raw).strip()
            # Identifiers are always upper-case on the document itself.
            if field.validator in {"pan", "gstin", "ifsc"}:
                text = text.upper().replace(" ", "")
            cleaned[field.name] = text

    # Preserve anything the model volunteered that isn't in the spec, rather
    # than silently dropping potentially useful data.
    for key, value in data.items():
        if key not in cleaned:
            cleaned[key] = value

    return cleaned


# --- Main entry point ---------------------------------------------------


def validate_document(
    document_type: DocumentType, parsed_data: dict[str, Any]
) -> tuple[ValidationStatus, list[dict], dict[str, Any]]:
    """
    Validate one parsed document.

    Returns (status, issues, normalised_data).

    Status logic:
      FAILED  - a mandatory field is missing, or a mandatory field's format is
                wrong. The document cannot be trusted.
      PARTIAL - only optional fields have problems, or a cross-check failed.
                Worth a human look but the core data is there.
      PASSED  - everything checks out.
    """
    spec = get_spec(document_type)
    if spec is None:
        return (
            ValidationStatus.FAILED,
            [FieldIssue("document_type", "unsupported_type",
                        f"No parser is defined for '{document_type}'")],
            parsed_data,
        )

    data = normalise_parsed_data(parsed_data, spec)
    issues: list[dict] = []
    has_mandatory_failure = False

    # --- Layer 1: presence and format ---
    for field in spec.fields:
        value = data.get(field.name)

        if value is None or value == "" or value == []:
            if field.mandatory:
                has_mandatory_failure = True
                issues.append(FieldIssue(
                    field.name, "mandatory_field",
                    f"{field.label} is required but was not found in the document",
                ))
            continue

        if field.validator:
            validator = FORMAT_VALIDATORS.get(field.validator)
            if validator:
                error = validator(value)
                if error:
                    severity = "error" if field.mandatory else "warning"
                    if field.mandatory:
                        has_mandatory_failure = True
                    issues.append(FieldIssue(
                        field.name, f"{field.validator}_format", error, severity
                    ))

        if field.type == FieldType.NUMBER and not isinstance(value, (int, float)):
            issues.append(FieldIssue(
                field.name, "number_format",
                f"{field.label} should be a number but got '{value}'",
                "error" if field.mandatory else "warning",
            ))
            if field.mandatory:
                has_mandatory_failure = True

    # --- Layer 2: arithmetic consistency ---
    for cross_check in spec.cross_checks:
        try:
            result = cross_check.check(data)
        except (TypeError, ValueError, ZeroDivisionError):
            result = None
        if result is False:
            issues.append(FieldIssue(
                "_cross_field", cross_check.name, cross_check.message, "warning"
            ))

    if has_mandatory_failure:
        status = ValidationStatus.FAILED
    elif issues:
        status = ValidationStatus.PARTIAL
    else:
        status = ValidationStatus.PASSED

    return status, issues, data


def completeness_score(document_type: DocumentType, data: dict[str, Any]) -> float:
    """
    Fraction of spec fields that were actually populated (0.0 - 1.0).

    Used alongside the model's self-reported confidence, because a model that
    is confidently wrong still leaves fields empty.
    """
    spec = get_spec(document_type)
    if spec is None or not spec.fields:
        return 0.0
    filled = sum(
        1 for f in spec.fields
        if data.get(f.name) not in (None, "", [], {})
    )
    return round(filled / len(spec.fields), 3)
