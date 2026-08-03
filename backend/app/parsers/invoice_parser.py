"""Invoice field specification."""

from app.models.enums import DocumentType
from app.parsers.base import DocumentSpec, FieldSpec, FieldType, balances_check

SPEC = DocumentSpec(
    document_type=DocumentType.INVOICE,
    label="Invoice",
    keywords=[
        "invoice", "tax invoice", "bill to", "ship to", "invoice no",
        "HSN", "SAC", "quantity", "rate", "amount", "subtotal",
        "grand total", "place of supply", "e-way bill",
    ],
    fields=[
        FieldSpec("invoice_number", "Invoice Number", FieldType.STRING,
                  "Invoice number as printed", mandatory=True,
                  example="INV-2024-0917"),
        FieldSpec("invoice_date", "Invoice Date", FieldType.DATE,
                  "Date of the invoice", mandatory=True, validator="date"),
        FieldSpec("due_date", "Due Date", FieldType.DATE,
                  "Payment due date if printed", validator="date"),
        FieldSpec("vendor_name", "Vendor Name", FieldType.STRING,
                  "Business issuing the invoice", mandatory=True),
        FieldSpec("customer_name", "Customer Name", FieldType.STRING,
                  "Business or person being billed", mandatory=True),
        FieldSpec("gst_number", "GST Number", FieldType.STRING,
                  "Vendor's GSTIN", validator="gstin"),
        FieldSpec("customer_gst_number", "Customer GSTIN", FieldType.STRING,
                  "Customer's GSTIN if printed", validator="gstin"),
        FieldSpec("taxable_amount", "Taxable Amount", FieldType.NUMBER,
                  "Subtotal before tax"),
        FieldSpec("tax_amount", "Tax Amount", FieldType.NUMBER,
                  "Total tax charged across CGST, SGST and IGST"),
        FieldSpec("invoice_amount", "Invoice Total", FieldType.NUMBER,
                  "Grand total payable including tax", mandatory=True),
        FieldSpec("currency", "Currency", FieldType.STRING,
                  "Currency code", example="INR"),
        FieldSpec("line_items", "Line Items", FieldType.ARRAY,
                  "Each line on the invoice. Every object must have: "
                  "description (string), hsn_sac (string or null), "
                  "quantity (number), rate (number), amount (number)"),
    ],
    cross_checks=[
        balances_check(
            "invoice_total_derivation",
            "Taxable amount plus tax does not equal the invoice total",
            ("taxable_amount", "tax_amount", "invoice_amount"),
            lambda ta, tx, total: abs((ta + tx) - total) <= 1.0,
        ),
        balances_check(
            "tax_plausibility",
            "Tax is more than 50% of the taxable amount, which is above any "
            "Indian GST slab",
            ("taxable_amount", "tax_amount"),
            lambda ta, tx: ta == 0 or (tx / ta) <= 0.50,
        ),
    ],
)
