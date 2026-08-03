"""
Validation engine tests.

No database, no API calls - these are pure functions, so the suite runs
offline in under a second.

    python -m tests.test_validation
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.enums import DocumentType, ValidationStatus  # noqa: E402
from app.services.validation_service import (  # noqa: E402
    coerce_number, parse_flexible_date, validate_document,
    validate_gstin, validate_pan, validate_ifsc,
)

PASSED = FAILED = 0


def check(label, condition, extra=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}  {extra}")


def main():
    print("\nGSTIN CHECKSUM (mod-36 check digit)")
    check("valid GSTIN accepted", validate_gstin("09AABCS1429B1ZS") is None,
          validate_gstin("09AABCS1429B1ZS") or "")
    check("O/S misread caught by checksum",
          validate_gstin("09AABCS1429B1ZO") is not None)
    check("wrong length rejected", validate_gstin("09AABCS1429") is not None)

    print("\nPAN FORMAT")
    check("valid PAN accepted", validate_pan("ABCPE1234F") is None)
    check("bad entity code in position 4 caught",
          validate_pan("ABCDE1234F") is not None)
    check("too short rejected", validate_pan("ABCPE123") is not None)

    print("\nIFSC FORMAT")
    check("valid IFSC accepted", validate_ifsc("HDFC0000123") is None)
    check("5th char must be zero", validate_ifsc("HDFC1000123") is not None)

    print("\nNUMBER COERCION")
    check("Rs. 45,000/- -> 45000", coerce_number("Rs. 45,000/-") == 45000.0,
          str(coerce_number("Rs. 45,000/-")))
    check("rupee symbol and decimals", coerce_number("\u20b91,20,000.50") == 120000.5)
    check("brackets mean negative", coerce_number("(1,200)") == -1200.0)
    check("lakh grouping", coerce_number("12,34,567") == 1234567.0)
    check("garbage returns None", coerce_number("abc") is None)

    print("\nDATE PARSING (Indian day-first convention)")
    d = parse_flexible_date("03/04/2024")
    check("03/04/2024 is 3rd April, not 4th March",
          d is not None and d.month == 4 and d.day == 3, str(d))
    check("31-Mar-2024 parsed", str(parse_flexible_date("31-Mar-2024")) == "2024-03-31")
    check("15 August 2023 parsed",
          str(parse_flexible_date("15 August 2023")) == "2023-08-15")

    print("\nCROSS-FIELD ARITHMETIC")
    status, issues, data = validate_document(DocumentType.SALARY_SLIP, {
        "employee_name": "Ananya Sharma", "company_name": "Infosys Ltd",
        "month": "March 2024", "gross_salary": "Rs. 85,000/-",
        "deductions": "12,500", "net_salary": "72500", "pan": "ABCPE1234F",
    })
    check("consistent salary slip passes", status == ValidationStatus.PASSED,
          f"{status} {issues}")
    check("currency string became a number", data["gross_salary"] == 85000.0)

    status, issues, _ = validate_document(DocumentType.SALARY_SLIP, {
        "employee_name": "Test", "company_name": "X", "month": "March 2024",
        "gross_salary": 85000, "deductions": 12500, "net_salary": 80000,
    })
    check("85000 - 12500 != 80000 is caught",
          any(i["rule"] == "net_salary_derivation" for i in issues), str(issues))

    status, issues, _ = validate_document(DocumentType.BALANCE_SHEET, {
        "total_assets": 5000000, "total_liabilities": 2000000, "equity": 2500000,
    })
    check("balance sheet that does not balance is caught",
          any(i["rule"] == "accounting_equation" for i in issues), str(issues))

    status, issues, _ = validate_document(DocumentType.GST_RETURN, {
        "gstin": "09AABCS1429B1ZS", "business_name": "X", "filing_period": "Mar 2024",
        "taxable_value": 100000, "cgst": 9000, "sgst": 5000,
        "igst": 0, "total_tax": 14000,
    })
    check("CGST != SGST on intra-state supply is caught",
          any(i["rule"] == "cgst_sgst_symmetry" for i in issues), str(issues))

    print("\nMANDATORY FIELDS")
    status, issues, _ = validate_document(DocumentType.INVOICE, {
        "invoice_number": "INV-001", "invoice_date": "2024-04-15",
        "vendor_name": "Sharma Traders",
    })
    check("missing mandatory fields fail hard", status == ValidationStatus.FAILED)
    check("both missing fields named",
          {i["field"] for i in issues} >= {"customer_name", "invoice_amount"},
          str([i["field"] for i in issues]))

    print(f"\n{'=' * 52}")
    print(f"  {PASSED} passed, {FAILED} failed")
    print(f"{'=' * 52}\n")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
