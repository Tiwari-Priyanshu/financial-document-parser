"""GST return field specification."""

from app.models.enums import DocumentType
from app.parsers.base import DocumentSpec, FieldSpec, FieldType, balances_check

SPEC = DocumentSpec(
    document_type=DocumentType.GST_RETURN,
    label="GST Return",
    keywords=[
        "GSTR-1", "GSTR-3B", "GSTR-9", "goods and services tax", "GSTIN",
        "CGST", "SGST", "IGST", "taxable value", "return period",
        "outward supplies", "input tax credit",
    ],
    fields=[
        FieldSpec("gstin", "GSTIN", FieldType.STRING,
                  "15-character GST Identification Number",
                  mandatory=True, validator="gstin", example="09AABCS1429B1ZS"),
        FieldSpec("business_name", "Business Name", FieldType.STRING,
                  "Legal or trade name of the registered business", mandatory=True),
        FieldSpec("return_type", "Return Type", FieldType.STRING,
                  "Which GST return this is", example="GSTR-3B"),
        FieldSpec("filing_period", "Filing Period", FieldType.STRING,
                  "Tax period covered", mandatory=True, example="March 2024"),
        FieldSpec("filing_date", "Filing Date", FieldType.DATE,
                  "Date the return was filed", validator="date"),
        FieldSpec("taxable_value", "Taxable Value", FieldType.NUMBER,
                  "Total taxable value of supplies", mandatory=True),
        FieldSpec("cgst", "CGST", FieldType.NUMBER, "Central GST amount"),
        FieldSpec("sgst", "SGST", FieldType.NUMBER, "State GST amount"),
        FieldSpec("igst", "IGST", FieldType.NUMBER, "Integrated GST amount"),
        FieldSpec("cess", "Cess", FieldType.NUMBER, "Cess amount, 0 if none"),
        FieldSpec("total_tax", "Total Tax", FieldType.NUMBER,
                  "Total tax payable", mandatory=True),
    ],
    cross_checks=[
        balances_check(
            "tax_components_sum",
            "CGST + SGST + IGST does not add up to the total tax",
            ("cgst", "sgst", "igst", "total_tax"),
            lambda c, s, i, t: abs((c + s + i) - t) <= 1.0,
        ),
        balances_check(
            "cgst_sgst_symmetry",
            "CGST and SGST differ - for intra-state supply they are always equal",
            ("cgst", "sgst"),
            lambda c, s: abs(c - s) <= 1.0 or c == 0 or s == 0,
        ),
    ],
)
