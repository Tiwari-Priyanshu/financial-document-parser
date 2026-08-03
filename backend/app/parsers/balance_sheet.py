"""Balance sheet field specification."""

from app.models.enums import DocumentType
from app.parsers.base import DocumentSpec, FieldSpec, FieldType, balances_check

SPEC = DocumentSpec(
    document_type=DocumentType.BALANCE_SHEET,
    label="Balance Sheet",
    keywords=[
        "balance sheet", "statement of financial position", "total assets",
        "total liabilities", "shareholders funds", "equity and liabilities",
        "non-current assets", "current liabilities", "reserves and surplus",
    ],
    fields=[
        FieldSpec("company_name", "Company Name", FieldType.STRING,
                  "Entity the balance sheet belongs to"),
        FieldSpec("as_on_date", "As On Date", FieldType.DATE,
                  "Date the balance sheet is drawn up to", validator="date"),
        FieldSpec("total_assets", "Total Assets", FieldType.NUMBER,
                  "Total of all assets", mandatory=True),
        FieldSpec("total_liabilities", "Total Liabilities", FieldType.NUMBER,
                  "Total of all liabilities", mandatory=True),
        FieldSpec("equity", "Equity", FieldType.NUMBER,
                  "Shareholders' equity or owner's capital", mandatory=True),
        FieldSpec("current_assets", "Current Assets", FieldType.NUMBER,
                  "Total current assets"),
        FieldSpec("fixed_assets", "Fixed Assets", FieldType.NUMBER,
                  "Total fixed or non-current assets"),
        FieldSpec("current_liabilities", "Current Liabilities", FieldType.NUMBER,
                  "Total current liabilities"),
    ],
    cross_checks=[
        balances_check(
            "accounting_equation",
            "Assets do not equal liabilities plus equity - the balance sheet "
            "does not balance",
            ("total_assets", "total_liabilities", "equity"),
            lambda a, l, e: abs(a - (l + e)) <= 10.0,
        ),
        balances_check(
            "asset_composition",
            "Current plus fixed assets exceed total assets",
            ("current_assets", "fixed_assets", "total_assets"),
            lambda c, f, t: (c + f) <= t + 10.0,
        ),
    ],
)
