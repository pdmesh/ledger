"""Shipped defaults: taxonomy, deterministic rules, settings and institution hints.

Everything here is seeded into the database on first run and is then fully user-editable.
Nothing here is personal data.
"""

from __future__ import annotations

from typing import Any

# (slug, name, description, children) -- roots carry the analytic role.
DEFAULT_TAXONOMY: list[dict[str, Any]] = [
    {
        "slug": "income",
        "name": "Income",
        "role": "income",
        "description": "Money earned from outside the household.",
        "children": [
            ("salary", "Salary", "Employment salary, wages, bonuses."),
            ("business-income", "Business income", "Freelance, consulting, business receipts."),
            ("rental-income", "Rental income", "Rent received from property."),
            ("interest", "Interest", "Interest credited on deposits or savings."),
            ("dividends", "Dividends", "Dividends from shares or funds."),
            ("other-income", "Other income", "Income not covered by another category."),
        ],
    },
    {
        "slug": "expense",
        "name": "Expenses",
        "role": "expense",
        "description": "Consumption spending that leaves the household.",
        "children": [
            ("living", "Living expenses", "Rent, household supplies, domestic help, maintenance."),
            ("groceries", "Groceries", "Supermarkets, grocery delivery, daily essentials."),
            ("food", "Food & dining", "Restaurants, cafes, food delivery."),
            ("shopping", "Shopping", "Retail, e-commerce, clothing, electronics."),
            ("travel", "Travel", "Flights, hotels, holidays."),
            ("transportation", "Transportation", "Fuel, taxis, ride-hailing, public transport."),
            ("healthcare", "Healthcare", "Doctors, hospitals, pharmacies, insurance premiums."),
            ("education", "Education", "School and college fees, courses, books."),
            ("entertainment", "Entertainment", "Movies, streaming, events, subscriptions."),
            ("utilities", "Utilities", "Electricity, water, gas, internet, mobile."),
            ("taxes-fees", "Taxes & fees", "Taxes, bank charges, late fees, government fees."),
            ("loan-interest", "Loan interest", "Interest component of loan repayments."),
            ("uncategorized", "Uncategorized", "Spending that could not yet be classified."),
        ],
    },
    {
        "slug": "investment",
        "name": "Investments",
        "role": "investment",
        "description": "Money moved into or out of investments (not consumption).",
        "children": [
            ("mutual-fund-purchase", "Mutual fund purchase", "Lump-sum or SIP fund purchases."),
            ("mutual-fund-redemption", "Mutual fund redemption", "Fund redemptions/withdrawals."),
            ("stock-purchase", "Stock purchase", "Equity purchases, broker funding."),
            ("stock-sale", "Stock sale", "Equity sale proceeds, broker payouts."),
            ("etf", "ETF transaction", "Exchange traded fund purchases or sales."),
            ("fixed-deposit", "Fixed deposit", "FD/term deposit creation or maturity."),
            ("retirement", "Retirement contribution", "Pension and retirement contributions."),
            ("other-investment", "Other investments", "Other investment cash movements."),
        ],
    },
    {
        "slug": "transfer",
        "name": "Financial movements",
        "role": "transfer",
        "description": "Movements between own accounts or settlement of liabilities.",
        "children": [
            ("internal-transfer", "Internal transfer", "Transfers between household accounts."),
            ("card-settlement", "Credit card settlement", "Paying a credit card bill."),
            ("loan-principal", "Loan principal repayment", "Principal portion of loan EMIs."),
            ("cash-withdrawal", "Cash withdrawal", "ATM or branch cash withdrawals."),
            ("cash-deposit", "Cash deposit", "Cash deposited into an account."),
            (
                "external-transfer",
                "Transfer to/from others",
                "Transfers to/from non-household people.",
            ),
        ],
    },
    {
        "slug": "adjustment",
        "name": "Adjustments",
        "role": "adjustment",
        "description": "Refunds, reversals and corrections to earlier transactions.",
        "children": [
            ("refund", "Refund", "Merchant refunds."),
            ("reversal", "Reversal", "Reversed or failed transactions."),
            ("chargeback", "Chargeback", "Disputed card transactions credited back."),
            ("cashback", "Cashback & rewards", "Cashback, reward redemptions."),
            ("other-adjustment", "Other adjustment", "Other corrections."),
        ],
    },
]

FALLBACK_OUTFLOW = "uncategorized"
FALLBACK_INFLOW = "other-income"


def _r(name: str, priority: int, category: str, words: list[str], **cond: Any) -> dict[str, Any]:
    return {
        "name": name,
        "priority": priority,
        "conditions": {"description_contains": words, **cond},
        "actions": {"category": category},
        "source": "system",
        "confidence": 0.85,
    }


# Generic, institution-agnostic keyword rules (word-boundary matches). Users can edit any.
DEFAULT_RULES: list[dict[str, Any]] = [
    _r("Reversals", 10, "reversal", ["reversal", "reversed", "rev:", "failed txn"]),
    _r("Refunds", 11, "refund", ["refund"], direction="inflow"),
    _r("Chargebacks", 12, "chargeback", ["chargeback"], direction="inflow"),
    _r("Cashback", 13, "cashback", ["cashback", "cash back", "reward"], direction="inflow"),
    _r(
        "Card payment received (card account)",
        20,
        "card-settlement",
        ["payment received", "payment - thank you", "payment thank you", "autopay", "bbps payment"],
        direction="inflow",
        account_types=["credit_card"],
    ),
    _r(
        "Credit card bill payment",
        21,
        "card-settlement",
        ["credit card", "creditcard", "card payment", "cc payment", "ccpay", "card bill"],
        direction="outflow",
        account_types=["savings", "current"],
    ),
    _r("Salary", 30, "salary", ["salary", "payroll", "sal cr", "wages"], direction="inflow"),
    _r(
        "Interest credit",
        31,
        "interest",
        ["interest", "int.pd", "int pd", "int cr"],
        direction="inflow",
    ),
    _r("Dividend", 32, "dividends", ["dividend", "div"], direction="inflow"),
    _r(
        "Mutual fund / SIP",
        40,
        "mutual-fund-purchase",
        ["mutual fund", "sip", "mf", "amc", "systematic investment"],
        direction="outflow",
    ),
    _r(
        "Mutual fund redemption",
        41,
        "mutual-fund-redemption",
        ["redemption", "mutual fund", "amc"],
        direction="inflow",
    ),
    _r(
        "Brokerage funding",
        42,
        "stock-purchase",
        ["brokerage", "securities", "demat"],
        direction="outflow",
    ),
    _r(
        "Fixed deposit",
        43,
        "fixed-deposit",
        ["fixed deposit", "term deposit", "fd", "fd booking", "fd closure", "fd maturity"],
    ),
    _r(
        "Retirement",
        44,
        "retirement",
        ["pension", "provident fund", "ppf", "nps", "401k", "epf"],
        direction="outflow",
    ),
    _r(
        "ATM cash",
        50,
        "cash-withdrawal",
        ["atm", "cash withdrawal", "atw", "nwd"],
        direction="outflow",
    ),
    _r("Cash deposit", 51, "cash-deposit", ["cash deposit", "cash dep", "cdm"], direction="inflow"),
    _r(
        "Loan EMI", 52, "loan-principal", ["emi", "loan repayment", "mortgage"], direction="outflow"
    ),
    _r(
        "Bank charges",
        60,
        "taxes-fees",
        [
            "charges",
            "fee",
            "gst",
            "annual fee",
            "late payment",
            "finance charge",
            "service tax",
            "tds",
        ],
        direction="outflow",
    ),
    _r(
        "Utilities",
        70,
        "utilities",
        [
            "electricity",
            "broadband",
            "internet",
            "mobile recharge",
            "postpaid",
            "water bill",
            "gas bill",
        ],
        direction="outflow",
    ),
    _r(
        "Fuel",
        71,
        "transportation",
        ["fuel", "petrol", "diesel", "filling station"],
        direction="outflow",
    ),
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "general": {
        "country": None,
        "base_currency": None,
        "locale": "en",
        "timezone": "UTC",
        "date_format": "auto",  # auto|DMY|MDY|YMD
        "decimal_separator": ".",
        "thousands_separator": ",",
        "onboarding_complete": False,
    },
    "ingestion": {
        "watch_folder": None,
        "watch_enabled": False,
        "poll_seconds": 30,
    },
    "reconciliation": {
        "transfer_window_days": 3,
        "settlement_window_days": 7,
        "refund_window_days": 120,
        "duplicate_min_confidence": 0.85,
    },
    "intelligence": {
        # Providers are user-configured. Nothing is enabled by default: the app works
        # fully deterministically until the user adds a provider.
        "providers": [],
        "routing": {},  # task -> [provider_id, fallback_provider_id, ...]
        "allow_cloud": False,
        "share_identity_names": False,  # include household names in cloud prompts
        "batch_size": 40,
    },
}

# Country presets only provide defaults; nothing is restricted to a country.
COUNTRY_PRESETS: dict[str, dict[str, str]] = {
    "IN": {"base_currency": "INR", "date_format": "DMY", "timezone": "Asia/Kolkata"},
    "US": {"base_currency": "USD", "date_format": "MDY", "timezone": "America/New_York"},
    "GB": {"base_currency": "GBP", "date_format": "DMY", "timezone": "Europe/London"},
    "DE": {
        "base_currency": "EUR",
        "date_format": "DMY",
        "timezone": "Europe/Berlin",
        "decimal_separator": ",",
        "thousands_separator": ".",
    },
    "FR": {
        "base_currency": "EUR",
        "date_format": "DMY",
        "timezone": "Europe/Paris",
        "decimal_separator": ",",
        "thousands_separator": " ",
    },
    "SG": {"base_currency": "SGD", "date_format": "DMY", "timezone": "Asia/Singapore"},
    "AE": {"base_currency": "AED", "date_format": "DMY", "timezone": "Asia/Dubai"},
    "AU": {"base_currency": "AUD", "date_format": "DMY", "timezone": "Australia/Sydney"},
    "CA": {"base_currency": "CAD", "date_format": "YMD", "timezone": "America/Toronto"},
}

# Public institution names used only as identification hints for statements. Users can
# register any other institution; identification also matches user-registered aliases.
INSTITUTION_HINTS: dict[str, list[str]] = {
    "HDFC Bank": ["hdfc bank", "hdfcbank"],
    "ICICI Bank": ["icici bank", "icicibank"],
    "State Bank of India": ["state bank of india", "sbi card", "sbi"],
    "Axis Bank": ["axis bank"],
    "Kotak Mahindra Bank": ["kotak mahindra", "kotak bank"],
    "IDFC FIRST Bank": ["idfc first"],
    "Yes Bank": ["yes bank"],
    "IndusInd Bank": ["indusind"],
    "American Express": ["american express", "amex"],
    "Citibank": ["citibank", "citi bank"],
    "HSBC": ["hsbc"],
    "Standard Chartered": ["standard chartered"],
    "Chase": ["jpmorgan chase", "chase bank", "chase.com"],
    "Bank of America": ["bank of america"],
    "Wells Fargo": ["wells fargo"],
    "Capital One": ["capital one"],
    "Barclays": ["barclays"],
    "Lloyds Bank": ["lloyds bank"],
    "DBS Bank": ["dbs bank"],
}
