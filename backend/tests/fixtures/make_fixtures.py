"""Generate the synthetic statement corpus used by the tests.

All institutions, people and numbers are fictional. Run from the backend directory:

    uv run python tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).parent


def northwind_jan() -> None:
    rows = [
        ("01/01/2026", "NEFT CR-ACME CORP-SALARY JAN 2026", "N0001", "", "150,000.00"),
        ("03/01/2026", "UPI/600112233/SWIGGY/swiggy@ybl", "U0002", "450.00", ""),
        ("05/01/2026", "IMPS-TRF TO OWN AC XX8765", "I0003", "20,000.00", ""),
        ("10/01/2026", "CC PAYMENT FABRIKAM CARD XX9988", "C0004", "30,000.00", ""),
        ("12/01/2026", "ACH D- EXAMPLE MUTUAL FUND SIP", "A0005", "10,000.00", ""),
        ("15/01/2026", "ATM WDL CASH 1234 MAIN ST", "W0006", "5,000.00", ""),
        ("18/01/2026", "UPI/600998877/SWIGGY/swiggy@ybl", "U0007", "620.00", ""),
        ("20/01/2026", "INTEREST CREDIT", "", "", "250.00"),
        ("25/01/2026", "UPI/600554433/RENT JAN/landlord@okaxis", "U0008", "25,000.00", ""),
    ]
    bal = 100000.0
    out = []
    for d, desc, ref, dr, cr in rows:
        bal += float(cr.replace(",", "") or 0) - float(dr.replace(",", "") or 0)
        out.append((d, desc, ref, dr, cr, f"{bal:,.2f}"))
    with (HERE / "northwind_savings_2026-01.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Northwind Bank"])
        w.writerow(["Statement of Account - Savings Account"])
        w.writerow(["Customer Name: Alex Sample"])
        w.writerow(["Account No: XXXXXXXX4321"])
        w.writerow(["Statement Period: 01/01/2026 to 31/01/2026"])
        w.writerow(["Opening Balance: 100,000.00"])
        w.writerow([f"Closing Balance: {bal:,.2f}"])
        w.writerow([])
        w.writerow(
            [
                "Date",
                "Narration",
                "Chq./Ref.No.",
                "Withdrawal Amt.",
                "Deposit Amt.",
                "Closing Balance",
            ]
        )
        w.writerows(out)


def northwind_overlap() -> None:
    """Overlapping statement (15 Jan - 10 Feb) exported in a different layout."""
    rows = [
        ("2026-01-15", "ATM WDL CASH 1234 MAIN ST", "W0006", "-5000.00"),
        ("2026-01-18", "UPI/600998877/SWIGGY/swiggy@ybl", "U0007", "-620.00"),
        ("2026-01-20", "INTEREST CREDIT", "", "250.00"),
        ("2026-01-25", "UPI/600554433/RENT JAN/landlord@okaxis", "U0008", "-25000.00"),
        ("2026-02-01", "NEFT CR-ACME CORP-SALARY FEB 2026", "N0009", "150000.00"),
        ("2026-02-03", "UPI/601112233/SWIGGY/swiggy@ybl", "U0010", "-380.00"),
    ]
    with (HERE / "northwind_savings_2026-01-15_to_02-10.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Northwind Bank", "Account Number", "XXXXXXXX4321"])
        w.writerow(["Transaction Date", "Description", "Reference", "Amount"])
        w.writerows(rows)


def contoso_jan() -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Contoso Bank"])
    ws.append(["Account Holder: Sam Sample"])
    ws.append(["Savings Account Number: 000011118765"])
    ws.append([])
    ws.append(["Txn Date", "Particulars", "Debit", "Credit", "Balance"])
    data = [
        ("05-01-2026", "IMPS FROM ALEX SAMPLE NORTHWIND", None, 20000.0),
        ("06-01-2026", "POS 4111XXXX BIGMART GROCERIES", 3200.0, None),
        ("28-01-2026", "SALARY GLOBEX LTD JAN", None, 90000.0),
        ("29-01-2026", "BILLPAY ELECTRICITY CITY POWER", 2100.0, None),
    ]
    bal = 50000.0
    for d, desc, dr, cr in data:
        bal += (cr or 0) - (dr or 0)
        ws.append([d, desc, dr, cr, bal])
    wb.save(HERE / "contoso_savings_2026-01.xlsx")


def fabrikam_card_pdf() -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(HERE / "fabrikam_card_2026-01.pdf"), pagesize=A4)
    y = 800
    lines = [
        "Fabrikam Card - Credit Card Statement",
        "Card Holder Name: Alex Sample",
        "Card Number: XXXX XXXX XXXX 9988",
        "Statement Period: 01/01/2026 to 31/01/2026",
        "Payment Due Date: 20/02/2026   Total Amount Due: 18,649.00   Minimum Amount Due: 1,000.00",
        "",
        "Date Transaction Details Amount (INR)",
        "02/01/2026 SWIGGY*INSTAMART BANGALORE 1,200.00",
        "04/01/2026 AMAZON PAY INDIA ORDER 18,000.00",
        "08/01/2026 STARBUCKS COFFEE MUMBAI 800.00",
        "11/01/2026 PAYMENT RECEIVED - THANK YOU 30,000.00 Cr",
        "15/01/2026 NETFLIX.COM SUBSCRIPTION 649.00",
        "20/01/2026 REFUND AMAZON PAY INDIA ORDER 2,000.00 Cr",
    ]
    for line in lines:
        c.drawString(40, y, line)
        y -= 18
    c.save()


if __name__ == "__main__":
    northwind_jan()
    northwind_overlap()
    contoso_jan()
    fabrikam_card_pdf()
    print("fixtures written to", HERE)
