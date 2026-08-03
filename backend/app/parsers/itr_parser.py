"""Income Tax Return field specification."""

from app.models.enums import DocumentType
from app.parsers.base import DocumentSpec, FieldSpec, FieldType, balances_check

SPEC = DocumentSpec(
    document_type=DocumentType.ITR,
    label="Income Tax Return",
    keywords=[
        "income tax return", "ITR-1", "ITR-2", "ITR-3", "ITR-4", "SAHAJ",
        "assessment year", "acknowledgement number", "gross total income",
        "chapter VI-A", "taxable income", "e-filing",
    ],
    fields=[
        FieldSpec("pan", "PAN", FieldType.STRING,
                  "10-character Permanent Account Number",
                  mandatory=True, validator="pan", example="ABCPE1234F"),
        FieldSpec("taxpayer_name", "Taxpayer Name", FieldType.STRING,
                  "Name of the assessee"),
        FieldSpec("assessment_year", "Assessment Year", FieldType.STRING,
                  "Assessment year", mandatory=True, example="2024-25"),
        FieldSpec("itr_form_type", "ITR Form", FieldType.STRING,
                  "Which ITR form was filed", example="ITR-1"),
        FieldSpec("filing_date", "Filing Date", FieldType.DATE,
                  "Date the return was filed", validator="date"),
        FieldSpec("acknowledgement_number", "Acknowledgement No.", FieldType.STRING,
                  "E-filing acknowledgement number"),
        FieldSpec("gross_income", "Gross Income", FieldType.NUMBER,
                  "Gross total income before deductions", mandatory=True),
        FieldSpec("total_deductions", "Total Deductions", FieldType.NUMBER,
                  "Total deductions claimed under Chapter VI-A"),
        FieldSpec("taxable_income", "Taxable Income", FieldType.NUMBER,
                  "Total income chargeable to tax after deductions"),
        FieldSpec("tax_paid", "Tax Paid", FieldType.NUMBER,
                  "Total tax paid including TDS, advance tax and self-assessment"),
        FieldSpec("refund", "Refund", FieldType.NUMBER,
                  "Refund due. Use 0 if none"),
    ],
    cross_checks=[
        balances_check(
            "taxable_income_derivation",
            "Gross income minus deductions does not equal taxable income",
            ("gross_income", "total_deductions", "taxable_income"),
            lambda g, d, t: abs((g - d) - t) <= 10.0,
        ),
        balances_check(
            "deductions_not_exceeding_income",
            "Total deductions exceed gross income, which is not possible",
            ("gross_income", "total_deductions"),
            lambda g, d: d <= g,
        ),
    ],
)
