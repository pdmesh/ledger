"""Passwords for protected PDF statements.

Passwords live in the OS keychain only, never in the database, job payloads or logs.
Two kinds are kept:

* a per-document password (keyed by the file's SHA-256), so the statement can be
  re-processed later, and
* a list of "known" passwords the user chose to remember. Issuers tend to reuse one
  password per person (often derived from name and date of birth), so new protected
  statements -- including folder imports -- are tried against this list automatically.

If the keychain is unavailable, values are kept in memory for the life of the process so
the current import still works.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ledger.intelligence.providers import KEYRING_SERVICE

log = logging.getLogger(__name__)

_KNOWN = "pdf-passwords"
_memory: dict[str, str] = {}


def _get(key: str) -> str | None:
    try:
        import keyring

        v = keyring.get_password(KEYRING_SERVICE, key)
        if v is not None:
            return v
    except Exception:  # keychain unavailable (e.g. headless Linux)
        pass
    return _memory.get(key)


def _set(key: str, value: str) -> bool:
    """Store a value; returns False if only the in-memory fallback could hold it."""
    _memory[key] = value
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, key, value)
        return True
    except Exception:
        log.warning("OS keychain unavailable; PDF password kept in memory until restart")
        return False


def known_passwords() -> list[str]:
    raw = _get(_KNOWN)
    try:
        values = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []
    return [v for v in values if isinstance(v, str) and v]


def remember_password(password: str) -> bool:
    values = known_passwords()
    if password in values:
        return True
    return _set(_KNOWN, json.dumps([password, *values][:50]))


def document_password(sha256: str) -> str | None:
    return _get(f"pdf:{sha256}")


def set_document_password(sha256: str, password: str) -> bool:
    return _set(f"pdf:{sha256}", password)


def is_encrypted(path: Path) -> bool:
    """True if the PDF cannot be opened without a user password."""
    return not opens_with(path, None)


def opens_with(path: Path, password: str | None) -> bool:
    import pypdfium2 as pdfium

    try:
        pdfium.PdfDocument(str(path), password=password or None).close()
        return True
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower():
            return False
        raise


def find_password(path: Path, sha256: str) -> tuple[bool, str | None]:
    """(opens, password). Tries no password, the document's own, then the known list."""
    if opens_with(path, None):
        return True, None
    candidates = [document_password(sha256), *known_passwords()]
    for pw in dict.fromkeys(c for c in candidates if c):
        if opens_with(path, pw):
            if document_password(sha256) != pw:
                set_document_password(sha256, pw)
            return True, pw
    return False, None
