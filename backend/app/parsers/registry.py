"""
Central registry of every supported document type.

The classifier, the extraction prompt builder, the validation engine and the
exporters all read from here.
"""

from typing import Optional

from app.models.enums import DocumentType
from app.parsers.base import DocumentSpec
from app.parsers import (
    balance_sheet, bank_statement, gst_parser, invoice_parser,
    itr_parser, pnl_parser, salary_parser,
)

SPECS: dict[DocumentType, DocumentSpec] = {
    spec.document_type: spec
    for spec in (
        bank_statement.SPEC,
        itr_parser.SPEC,
        gst_parser.SPEC,
        salary_parser.SPEC,
        invoice_parser.SPEC,
        balance_sheet.SPEC,
        pnl_parser.SPEC,
    )
}

# Types the classifier is allowed to choose from.
CLASSIFIABLE_TYPES: list[DocumentType] = list(SPECS.keys())


def get_spec(document_type: DocumentType) -> Optional[DocumentSpec]:
    return SPECS.get(document_type)


def classification_reference() -> str:
    """Bullet list of type -> tell-tale phrases, injected into the classifier prompt."""
    lines = []
    for doc_type, spec in SPECS.items():
        keywords = ", ".join(spec.keywords[:8])
        lines.append(f'- "{doc_type.value}" ({spec.label}): look for {keywords}')
    return "\n".join(lines)
