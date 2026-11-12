"""Statement-level metadata detection from header/preamble text."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ledger.defaults import INSTITUTION_HINTS
from ledger.ingestion.parsing import (
    DATE_TOKEN,
    StatementMetadata,
    parse_amount,
    parse_date,
)
from ledger.text import contains_word, last4

CARD_WORDS = (
    "credit card",
    "card statement",
    "minimum amount due",
    "minimum due",
    "payment due date",
    "total amount due",
    "credit limit",
    "available credit",
    "card number",
    "card no",
)
INVESTMENT_WORDS = ("consolidated account statement", "folio", "nav", "units", "demat", "holdings")
BANK_WORDS = (
    "savings account",
    "current account",
    "account statement",
    "statement of account",
    "opening balance",
    "closing balance",
    "account no",
    "account number",
    "ifsc",
)

_ACCT = re.compile(
    r"(?:a/c|acct|account|card)\s*(?:no|number|num|#)?\.?\s*[:\-]?\s*"
    r"((?:[0-9Xx*•]{2,}[\s\-]?){2,}[0-9]{2,})",
    re.I,
)
_PERIOD = re.compile(
    r"(?:statement\s+period|period|from|for\s+the\s+period)\s*[:\-]?\s*(?P<a>.{6,20}?)\s*"
    r"(?:to|till|until|-|–|through)\s*(?P<b>.{6,20})",
    re.I,
)
_OPEN = re.compile(
    r"opening\s+balance[^0-9\-(]{0,20}([\-(]?[\d,]+\.\d{1,2}\)?(?:\s*(?:cr|dr))?)", re.I
)
_CLOSE = re.compile(
    r"closing\s+balance[^0-9\-(]{0,20}([\-(]?[\d,]+\.\d{1,2}\)?(?:\s*(?:cr|dr))?)", re.I
)
_CURRENCY_CODES = ("INR", "USD", "EUR", "GBP", "SGD", "AED", "AUD", "CAD", "JPY", "CHF", "HKD")
_SYMBOLS = {"₹": "INR", "€": "EUR", "£": "GBP", "¥": "JPY"}
_HOLDER = re.compile(
    r"(?:customer\s+name|account\s+holder(?:\s+name)?|name\s+of\s+(?:the\s+)?customer|"
    r"card\s*holder(?:\s+name)?|primary\s+card\s*holder|name)\s*[:\-]\s*([^\n]{3,80})",
    re.I,
)


def detect_institution(text_norm: str, extra: Iterable[tuple[str, list[str]]] = ()) -> str | None:
    """Match known institution names. ``extra`` = user-registered (name, aliases)."""
    for name, aliases in list(extra) + list(INSTITUTION_HINTS.items()):
        for alias in [name, *aliases]:
            if alias and contains_word(text_norm, alias.lower()):
                return name
    return None


def detect_metadata(
    header_text: str,
    *,
    date_order: str = "DMY",
    known_institutions: Iterable[tuple[str, list[str]]] = (),
    filename: str = "",
) -> StatementMetadata:
    md = StatementMetadata()
    text = header_text or ""
    norm = re.sub(r"\s+", " ", text.lower())
    md.institution = detect_institution(norm + " " + filename.lower(), known_institutions)

    card_hits = sum(w in norm for w in CARD_WORDS)
    inv_hits = sum(contains_word(norm, w) for w in INVESTMENT_WORDS)
    bank_hits = sum(w in norm for w in BANK_WORDS)
    if card_hits >= 2 or (card_hits and "card" in filename.lower()):
        md.document_type, md.account_type = "credit_card_statement", "credit_card"
    elif inv_hits >= 2 and inv_hits > bank_hits:
        md.document_type, md.account_type = "investment_statement", "investment"
    else:
        md.document_type = "bank_statement"
        md.account_type = "current" if "current account" in norm else "savings"
    md.evidence["type_scores"] = {"card": card_hits, "investment": inv_hits, "bank": bank_hits}

    m = _ACCT.search(text)
    if m:
        md.account_number_last4 = last4(m.group(1))

    m = _PERIOD.search(text)
    if m:
        a = DATE_TOKEN.search(m.group("a"))
        b = DATE_TOKEN.search(m.group("b"))
        if a and b:
            md.period_start = parse_date(a.group(0), date_order)
            md.period_end = parse_date(b.group(0), date_order)

    for code in _CURRENCY_CODES:
        if re.search(rf"\b{code}\b", text):
            md.currency = code
            break
    if not md.currency:
        for sym, code in _SYMBOLS.items():
            if sym in text:
                md.currency = code
                break

    for rx, attr in ((_OPEN, "opening_balance"), (_CLOSE, "closing_balance")):
        m = rx.search(text)
        if m:
            pa = parse_amount(m.group(1))
            if pa:
                setattr(md, attr, pa.value * (-1 if pa.explicit_sign < 0 else 1))

    holders = [h.strip() for h in _HOLDER.findall(text)]
    if holders:
        md.holder_text = "; ".join(dict.fromkeys(holders))
    return md
