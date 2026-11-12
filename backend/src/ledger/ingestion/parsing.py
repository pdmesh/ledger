"""Locale-tolerant date and amount parsing plus shared extraction data structures."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for m in names
}

_NUMERIC_DATE = re.compile(r"^\s*(\d{1,4})[./\-\s](\d{1,2})[./\-\s](\d{2,4})")
_TEXT_DATE_DMY = re.compile(r"^\s*(\d{1,2})[\s\-./]*([A-Za-z]{3,9})[\s\-./,]*(\d{2,4})")
_TEXT_DATE_MDY = re.compile(
    r"^\s*([A-Za-z]{3,9})[\s\-./]*(\d{1,2})(?:st|nd|rd|th)?[\s,\-./]+(\d{2,4})"
)
DATE_TOKEN = re.compile(
    r"\b(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[\s\-][A-Za-z]{3,9}[\s\-,]*\d{2,4}|[A-Za-z]{3,9}\s\d{1,2},?\s\d{4})\b"
)


def _year(y: int) -> int:
    if y < 100:
        return 2000 + y if y < 70 else 1900 + y
    return y


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(_year(y), m, d)
    except ValueError:
        return None


def parse_date(value: Any, order: str = "DMY") -> date | None:
    """Parse a date in many common statement formats.

    ``order`` resolves ambiguous numeric dates (``DMY``, ``MDY`` or ``YMD``).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    m = _NUMERIC_DATE.match(s)
    if m:
        a, b, c = (int(x) for x in m.groups())
        if len(m.group(1)) == 4:  # YYYY-MM-DD
            return _safe_date(a, b, c)
        if order == "MDY":
            return _safe_date(c, a, b) or _safe_date(c, b, a)
        return _safe_date(c, b, a) or _safe_date(c, a, b)
    m = _TEXT_DATE_DMY.match(s)
    if m and m.group(2).lower() in MONTHS:
        return _safe_date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
    m = _TEXT_DATE_MDY.match(s)
    if m and m.group(1).lower() in MONTHS:
        return _safe_date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
    return None


def infer_date_order(samples: list[str], default: str = "DMY") -> str:
    """Infer DMY vs MDY from unambiguous samples (a component > 12)."""
    dmy = mdy = 0
    for s in samples:
        m = _NUMERIC_DATE.match(str(s))
        if not m or len(m.group(1)) == 4:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 >= b:
            dmy += 1
        elif b > 12 >= a:
            mdy += 1
    if dmy > mdy:
        return "DMY"
    if mdy > dmy:
        return "MDY"
    return default if default in ("DMY", "MDY") else "DMY"


_CR = re.compile(r"\b(cr|credit)\b\.?$", re.I)
_DR = re.compile(r"\b(dr|debit)\b\.?$", re.I)


@dataclass
class ParsedAmount:
    value: Decimal  # absolute value unless an explicit sign was present
    explicit_sign: int  # -1, +1 or 0 when no sign/indicator was present
    indicator: bool = False  # sign came from a textual Cr/Dr marker rather than +/-/()


def parse_amount(value: Any, decimal_sep: str = ".") -> ParsedAmount | None:
    """Parse amounts like ``1,23,456.78``, ``(12.50)``, ``-5``, ``1.234,56``, ``500.00 Cr``."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        d = Decimal(str(value))
        return ParsedAmount(abs(d), -1 if d < 0 else (1 if d > 0 else 0))
    s = str(value).strip()
    if not s or s in {"-", "--", "nil", "NIL"}:
        return None
    sign = 0
    indicator = False
    if _CR.search(s):
        sign, indicator = 1, True
        s = _CR.sub("", s).strip()
    elif _DR.search(s):
        sign, indicator = -1, True
        s = _DR.sub("", s).strip()
    if s.startswith("(") and s.endswith(")"):
        sign = -1
        s = s[1:-1]
    # strip currency symbols/codes
    s = re.sub(r"[A-Za-z₹$€£¥\s]", "", s)
    if s.startswith("+"):
        sign = sign or 1
        s = s[1:]
    if s.startswith("-") or s.endswith("-"):
        sign = -1
        s = s.strip("-")
    if not s or not re.search(r"\d", s):
        return None
    if decimal_sep == ",":
        s = s.replace(".", "").replace(" ", "").replace(",", ".")
    else:
        s = s.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    try:
        return ParsedAmount(Decimal(s), sign, indicator)
    except InvalidOperation:
        return None


@dataclass
class ParsedRow:
    txn_date: date
    description: str
    amount: Decimal  # signed, + inflow / - outflow (from the account's perspective)
    posting_date: date | None = None
    currency: str | None = None
    reference: str | None = None
    balance: Decimal | None = None
    source_ref: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    sign_basis: str = "column"  # column|indicator|balance|convention|llm


@dataclass
class StatementMetadata:
    institution: str | None = None
    document_type: str | None = None  # bank_statement|credit_card_statement|investment_statement
    account_type: str | None = None
    account_number_last4: str | None = None
    holder_text: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    currency: str | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedStatement:
    rows: list[ParsedRow]
    header_text: str
    metadata: StatementMetadata
    method: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParseOptions:
    date_order: str = "auto"  # auto|DMY|MDY|YMD
    decimal_sep: str = "."
    default_currency: str | None = None
    default_date_order: str = "DMY"  # used when auto inference is inconclusive
