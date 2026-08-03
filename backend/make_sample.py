"""Generate a realistic Indian tax invoice for testing extraction."""

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

c = canvas.Canvas("/Users/priyanshukumartiwari/Desktop/sample_invoice.pdf", pagesize=A4)
y = 800

def line(text, size=10, bold=False, dy=18):
    global y
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(50, y, text)
    y -= dy

line("TAX INVOICE", 16, True, 30)
line("Sharma Traders Private Limited", 12, True)
line("14/2 Nehru Place, New Delhi - 110019")
line("GSTIN: 09AABCS1429B1ZS")
line("State: Uttar Pradesh (09)", dy=28)

line("Invoice No: INV-2024-0917")
line("Invoice Date: 17/09/2024")
line("Due Date: 17/10/2024", dy=28)

line("Bill To:", 11, True)
line("Bharat Enterprises")
line("22 MG Road, Noida - 201301")
line("GSTIN: 09AAGCB7383J1Z6", dy=28)

line("Description            HSN      Qty    Rate      Amount", 10, True)
line("Consulting Services    998311     1   40000.00   40,000.00")
line("Software License       998434     2    5000.00   10,000.00", dy=28)

line("Taxable Value:        Rs. 50,000.00")
line("CGST @ 9%:            Rs.  4,500.00")
line("SGST @ 9%:            Rs.  4,500.00")
line("Total Tax:            Rs.  9,000.00")
line("Grand Total:          Rs. 59,000.00", 12, True)

c.save()
print("Created sample_invoice.pdf on your Desktop")
