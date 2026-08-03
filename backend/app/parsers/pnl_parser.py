"""Profit & Loss statement field specification."""

from app.models.enums import DocumentType
from app.parsers.base import DocumentSpec, FieldSpec, FieldType, balances_check

SPEC = DocumentSpec(
    document_type=DocumentType.PROFIT_LOSS,
    label="Profit & Loss Statement",
    keywords=[
        "profit and loss", "profit & loss", "statement of profit and loss",
        "income statement", "revenue from operations", "gross profit",
        "operating expenses", "EBITDA", "net profit", "cost of goods sold",
    ],
    fields=[
        FieldSpec("company_name", "Company Name", FieldType.STRING,
                  "Entity the statement belongs to"),
        FieldSpec("period", "Period", FieldType.STRING,
                  "Period covered", example="FY 2023-24"),
        FieldSpec("revenue", "Revenue", FieldType.NUMBER,
                  "Total revenue or turnover", mandatory=True),
        FieldSpec("cost_of_goods_sold", "Cost of Goods Sold", FieldType.NUMBER,
                  "Direct costs attributable to production"),
        FieldSpec("gross_profit", "Gross Profit", FieldType.NUMBER,
                  "Revenue minus cost of goods sold"),
        FieldSpec("operating_expenses", "Operating Expenses", FieldType.NUMBER,
                  "Total operating expenses"),
        FieldSpec("ebitda", "EBITDA", FieldType.NUMBER,
                  "Earnings before interest, tax, depreciation and amortisation"),
        FieldSpec("depreciation", "Depreciation", FieldType.NUMBER,
                  "Depreciation and amortisation"),
        FieldSpec("interest", "Interest / Finance Cost", FieldType.NUMBER,
                  "Finance costs"),
        FieldSpec("tax_expense", "Tax Expense", FieldType.NUMBER,
                  "Income tax expense"),
        FieldSpec("net_profit", "Net Profit", FieldType.NUMBER,
                  "Profit after tax. Negative if a loss", mandatory=True),
    ],
    cross_checks=[
        balances_check(
            "gross_profit_derivation",
            "Revenue minus cost of goods sold does not equal gross profit",
            ("revenue", "cost_of_goods_sold", "gross_profit"),
            lambda r, c, g: abs((r - c) - g) <= 10.0,
        ),
        balances_check(
            "net_profit_ceiling",
            "Net profit exceeds gross profit, which cannot happen after "
            "operating expenses and tax",
            ("gross_profit", "net_profit"),
            lambda g, n: n <= g + 10.0,
        ),
    ],
)
