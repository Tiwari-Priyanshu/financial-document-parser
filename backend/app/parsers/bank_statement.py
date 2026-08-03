"""Bank statement field specification."""

from app.models.enums import DocumentType
from app.parsers.base import (
    CrossCheck, DocumentSpec, FieldSpec, FieldType, balances_check,
)

SPEC = DocumentSpec(
    document_type=DocumentType.BANK_STATEMENT,
    label="Bank Statement",
    keywords=[
        "statement of account", "account statement", "opening balance",
        "closing balance", "withdrawal", "deposit", "IFSC", "branch",
        "value date", "narration", "chq no",
    ],
    fields=[
        FieldSpec("bank_name", "Bank Name", FieldType.STRING,
                  "Name of the bank issuing the statement", mandatory=True,
                  example="HDFC Bank Ltd"),
        FieldSpec("account_holder", "Account Holder", FieldType.STRING,
                  "Full name of the account holder", mandatory=True),
        FieldSpec("account_number", "Account Number", FieldType.STRING,
                  "Bank account number, digits only. If it is masked "
                  "(e.g. XXXXXX1234) return it exactly as printed",
                  mandatory=True, validator="account_number"),
        FieldSpec("ifsc_code", "IFSC Code", FieldType.STRING,
                  "11-character IFSC code of the branch",
                  validator="ifsc", example="HDFC0000123"),
        FieldSpec("statement_period", "Statement Period", FieldType.STRING,
                  "Period the statement covers, as printed",
                  example="01-04-2024 to 30-06-2024"),
        FieldSpec("period_from", "Period From", FieldType.DATE,
                  "First day of the statement period", validator="date"),
        FieldSpec("period_to", "Period To", FieldType.DATE,
                  "Last day of the statement period", validator="date"),
        FieldSpec("opening_balance", "Opening Balance", FieldType.NUMBER,
                  "Balance at the start of the period", mandatory=True),
        FieldSpec("closing_balance", "Closing Balance", FieldType.NUMBER,
                  "Balance at the end of the period", mandatory=True),
        FieldSpec("total_credits", "Total Credits", FieldType.NUMBER,
                  "Sum of all money coming in during the period"),
        FieldSpec("total_debits", "Total Debits", FieldType.NUMBER,
                  "Sum of all money going out during the period"),
        FieldSpec("transaction_count", "Transaction Count", FieldType.NUMBER,
                  "Total number of transaction rows in the statement"),
        FieldSpec("transactions", "Transactions", FieldType.ARRAY,
                  "Every transaction row. Each object must have: date "
                  "(YYYY-MM-DD), description (string), debit (number or null), "
                  "credit (number or null), balance (number or null)"),
    ],
    cross_checks=[
        balances_check(
            "balance_reconciliation",
            "Opening balance + credits - debits does not equal the closing balance",
            ("opening_balance", "total_credits", "total_debits", "closing_balance"),
            lambda o, c, d, cl: abs((o + c - d) - cl) <= 1.0,
        ),
        CrossCheck(
            name="transaction_count_matches",
            message="Transaction count does not match the number of rows extracted",
            check=lambda d: (
                None
                if d.get("transaction_count") in (None, "")
                or not isinstance(d.get("transactions"), list)
                else abs(int(float(d["transaction_count"])) - len(d["transactions"])) <= 0
            ),
        ),
    ],
)
