"""Salary slip field specification."""

from app.models.enums import DocumentType
from app.parsers.base import DocumentSpec, FieldSpec, FieldType, balances_check

SPEC = DocumentSpec(
    document_type=DocumentType.SALARY_SLIP,
    label="Salary Slip",
    keywords=[
        "salary slip", "pay slip", "payslip", "earnings", "deductions",
        "basic", "HRA", "gross salary", "net pay", "take home",
        "employee code", "provident fund", "professional tax", "LOP",
    ],
    fields=[
        FieldSpec("employee_name", "Employee Name", FieldType.STRING,
                  "Full name of the employee", mandatory=True),
        FieldSpec("company_name", "Company Name", FieldType.STRING,
                  "Name of the employer", mandatory=True),
        FieldSpec("employee_id", "Employee ID", FieldType.STRING,
                  "Employee code or ID"),
        FieldSpec("designation", "Designation", FieldType.STRING,
                  "Job title, if printed"),
        FieldSpec("pan", "PAN", FieldType.STRING,
                  "Employee's PAN if printed", validator="pan"),
        FieldSpec("month", "Pay Period", FieldType.STRING,
                  "Month and year this slip covers",
                  mandatory=True, example="March 2024"),
        FieldSpec("gross_salary", "Gross Salary", FieldType.NUMBER,
                  "Total earnings before any deductions", mandatory=True),
        FieldSpec("basic_salary", "Basic Salary", FieldType.NUMBER,
                  "Basic pay component"),
        FieldSpec("hra", "HRA", FieldType.NUMBER, "House rent allowance"),
        FieldSpec("deductions", "Total Deductions", FieldType.NUMBER,
                  "Sum of all deductions"),
        FieldSpec("pf", "Provident Fund", FieldType.NUMBER,
                  "Employee PF contribution"),
        FieldSpec("professional_tax", "Professional Tax", FieldType.NUMBER,
                  "Professional tax deducted"),
        FieldSpec("income_tax", "Income Tax / TDS", FieldType.NUMBER,
                  "Income tax or TDS deducted"),
        FieldSpec("net_salary", "Net Salary", FieldType.NUMBER,
                  "Take-home pay after deductions", mandatory=True),
    ],
    cross_checks=[
        balances_check(
            "net_salary_derivation",
            "Gross salary minus deductions does not equal net salary",
            ("gross_salary", "deductions", "net_salary"),
            lambda g, d, n: abs((g - d) - n) <= 1.0,
        ),
        balances_check(
            "net_not_above_gross",
            "Net salary is greater than gross salary",
            ("gross_salary", "net_salary"),
            lambda g, n: n <= g,
        ),
        balances_check(
            "basic_within_gross",
            "Basic salary exceeds gross salary",
            ("gross_salary", "basic_salary"),
            lambda g, b: b <= g,
        ),
    ],
)
