from datetime import date
from decimal import Decimal

from ledger.ingestion.parsing import infer_date_order, parse_amount, parse_date
from ledger.text import merchant_key


def test_amounts():
    assert parse_amount("1,23,456.78").value == Decimal("123456.78")
    a = parse_amount("(12.50)")
    assert a.value == Decimal("12.50") and a.explicit_sign == -1
    a = parse_amount("500.00 Cr")
    assert a.explicit_sign == 1 and a.indicator
    assert parse_amount("1.234,56", decimal_sep=",").value == Decimal("1234.56")
    assert parse_amount("₹ 2,000").value == Decimal("2000")
    assert parse_amount("") is None and parse_amount("abc") is None


def test_dates():
    assert parse_date("05/01/2026", "DMY") == date(2026, 1, 5)
    assert parse_date("05/01/2026", "MDY") == date(2026, 5, 1)
    assert parse_date("2026-01-05") == date(2026, 1, 5)
    assert parse_date("5 Jan 2026") == date(2026, 1, 5)
    assert parse_date("Jan 5, 2026") == date(2026, 1, 5)
    assert parse_date("05-Jan-26") == date(2026, 1, 5)
    assert infer_date_order(["13/01/2026", "02/01/2026"]) == "DMY"
    assert infer_date_order(["01/13/2026"]) == "MDY"


def test_merchant_keys():
    assert merchant_key("UPI/600112233/SWIGGY/swiggy@ybl") == "swiggy"
    assert merchant_key("SWIGGY*INSTAMART BANGALORE") == "swiggy"
    assert merchant_key("REFUND AMAZON PAY INDIA ORDER") == merchant_key("AMAZON PAY INDIA ORDER")
