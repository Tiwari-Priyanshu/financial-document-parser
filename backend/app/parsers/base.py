"""
Parser specification framework.

Every supported document type is described declaratively as a DocumentSpec:
which fields to pull out, which are mandatory, which format validator applies,
and which arithmetic relationships should hold between them.

Everything downstream is driven by these specs - the AI prompt, the validation
engine, the export columns and the frontend's review form are all generated
from them. Adding an eighth document type means writing one new file in this
folder and registering it. No other module changes.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from app.models.enums import DocumentType


class FieldType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    DATE = "date"
    ARRAY = "array"


@dataclass(frozen=True)
class FieldSpec:
    """One extractable field."""

    name: str                       # snake_case key in parsed_data
    label: str                      # human label for the UI and reports
    type: FieldType
    description: str                # instruction handed to the model
    mandatory: bool = False
    validator: Optional[str] = None  # key into validation_service.FORMAT_VALIDATORS
    example: Optional[str] = None


@dataclass(frozen=True)
class CrossCheck:
    """
    An arithmetic relationship that should hold between extracted values.

    This is what separates "the AI returned some numbers" from "the numbers are
    internally consistent". If a bank statement's opening balance plus credits
    minus debits does not land on the closing balance, something was misread and
    the document needs a human look.
    """

    name: str
    message: str
    check: Callable[[dict], Optional[bool]]  # None => not enough data to judge
    tolerance: float = 1.0                   # rupees, absorbs rounding


@dataclass(frozen=True)
class DocumentSpec:
    document_type: DocumentType
    label: str
    # Phrases that strongly indicate this document type. Used to give the
    # classifier concrete anchors instead of relying on the label alone.
    keywords: list[str] = field(default_factory=list)
    fields: list[FieldSpec] = field(default_factory=list)
    cross_checks: list[CrossCheck] = field(default_factory=list)

    @property
    def mandatory_fields(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.mandatory]

    def field_by_name(self, name: str) -> Optional[FieldSpec]:
        return next((f for f in self.fields if f.name == name), None)

    def json_shape(self) -> str:
        """
        Render the expected JSON shape for the extraction prompt.

        Being explicit about types here measurably cuts down on the model
        returning "Rs. 45,000/-" where a number was wanted.
        """
        lines = []
        for f in self.fields:
            if f.type == FieldType.NUMBER:
                hint = "number, digits only, no currency symbols or commas"
            elif f.type == FieldType.DATE:
                hint = "string in YYYY-MM-DD format"
            elif f.type == FieldType.ARRAY:
                hint = "array of objects"
            else:
                hint = "string"
            note = f" (e.g. {f.example})" if f.example else ""
            lines.append(f'  "{f.name}": <{hint}>  // {f.description}{note}')
        return "{\n" + ",\n".join(lines) + "\n}"


def _num(data: dict, key: str) -> Optional[float]:
    """Read a numeric field, returning None if absent or unparseable."""
    value = data.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def balances_check(
    name: str, message: str, keys: tuple[str, ...], relation: Callable[..., bool],
    tolerance: float = 1.0,
) -> CrossCheck:
    """Build a CrossCheck that only fires when every required number is present."""

    def _check(data: dict) -> Optional[bool]:
        values = [_num(data, k) for k in keys]
        if any(v is None for v in values):
            return None  # can't judge, don't penalise
        return relation(*values)

    return CrossCheck(name=name, message=message, check=_check, tolerance=tolerance)
