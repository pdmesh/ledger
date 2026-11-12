"""Deterministic text normalization used across identity, merchant and rule matching."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Payment-rail and statement noise tokens that never identify a merchant.
MONTHS = {
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "january",
    "february",
    "march",
    "april",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}

NOISE_TOKENS = MONTHS | {
    "cc",
    "wdl",
    "salary",
    "sal",
    "received",
    "thank",
    "you",
    "bill",
    "emi",
    "upi",
    "pos",
    "neft",
    "imps",
    "rtgs",
    "ach",
    "nach",
    "ecs",
    "ecom",
    "ecomm",
    "txn",
    "trf",
    "transfer",
    "to",
    "from",
    "by",
    "via",
    "ref",
    "refno",
    "no",
    "dr",
    "cr",
    "debit",
    "credit",
    "card",
    "purchase",
    "payment",
    "pmt",
    "paid",
    "online",
    "int",
    "intl",
    "inr",
    "usd",
    "eur",
    "gbp",
    "mb",
    "ib",
    "bil",
    "billpay",
    "vps",
    "vin",
    "mmt",
    "si",
    "auto",
    "debit card",
    "visa",
    "mastercard",
    "rupay",
    "contactless",
    "tap",
    "the",
    "of",
    "pvt",
    "ltd",
    "limited",
    "private",
    "inc",
    "llc",
    "corp",
    "co",
    "india",
    "www",
    "com",
    "in",
    "net",
    "org",
    "p2m",
    "p2a",
    "collect",
    "request",
    "pay",
    "ok",
    "refund",
    "reversal",
    "rev",
    "order",
    "chargeback",
    "okicici",
    "okhdfcbank",
    "oksbi",
    "okaxis",
    "ybl",
    "paytm",
    "apl",
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(s: str) -> str:
    """Normalize a personal or account-holder name: lowercase, no punctuation/titles."""
    s = strip_accents(s).lower()
    s = re.sub(r"\b(mr|mrs|ms|miss|dr|shri|smt|kumari|m/s)\b\.?", " ", s)
    s = _NON_ALNUM.sub(" ", s)
    return _WS.sub(" ", s).strip()


def normalize_description(s: str) -> str:
    """Lowercased, whitespace-collapsed description; keeps digits for references."""
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9@&./*\- ]+", " ", s)
    return _WS.sub(" ", s).strip()


def tokens(s: str) -> list[str]:
    return [t for t in _NON_ALNUM.split(strip_accents(s).lower()) if t]


def _is_noise(tok: str) -> bool:
    if tok in NOISE_TOKENS or len(tok) < 2:
        return True
    if tok.isdigit():
        return True
    # mostly-digit reference ids like "ab12345678"
    digits = sum(c.isdigit() for c in tok)
    return digits >= 4 and digits / len(tok) > 0.4


def merchant_key(description: str) -> str:
    """Best-effort merchant key from a raw transaction description.

    ``UPI/123456789/SWIGGY/swiggy@ybl`` -> ``swiggy``;
    ``POS 4321XXXX STARBUCKS COFFEE MUMBAI`` -> ``starbucks coffee mumbai``.
    The key is intentionally coarse; aliases map keys to canonical merchants.
    """
    s = strip_accents(description).lower()
    # VPA handles: keep the user part before '@'
    s = re.sub(r"([a-z0-9._-]+)@[a-z0-9.]+", lambda m: " " + m.group(1) + " ", s)
    parts = re.split(r"[/|*\-_:,]+", s)
    meaningful: list[list[str]] = []
    for part in parts:
        toks = [t for t in _NON_ALNUM.split(part) if t and not _is_noise(t)]
        if toks:
            meaningful.append(toks)
    if not meaningful:
        return ""
    # first meaningful segment, at most 3 tokens
    return " ".join(meaningful[0][:3])


def contains_word(haystack_norm: str, needle: str) -> bool:
    """Word-boundary containment on normalized text (needle may contain spaces/punct)."""
    needle = needle.lower().strip()
    if not needle:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    return re.search(pattern, haystack_norm) is not None


def slugify(s: str) -> str:
    return _NON_ALNUM.sub("-", strip_accents(s).lower()).strip("-") or "item"


def jaccard(a: str, b: str) -> float:
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def last4(s: str | None) -> str | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    return digits[-4:] if len(digits) >= 4 else None
