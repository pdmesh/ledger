"""Identity and account-ownership resolution.

Ownership is inferred at the *account* level from statement evidence (holder name block,
header text), never guessed per transaction.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger.models import Account, AccountOwner, Identity
from ledger.text import contains_word, normalize_name


@dataclass
class IdentityMatch:
    identity_id: int
    matched: str
    score: float


def identity_names(ident: Identity) -> list[str]:
    names = [ident.display_name, ident.legal_name or ""] + [a.alias for a in ident.aliases]
    out = []
    for n in names:
        nn = normalize_name(n)
        if len(nn) >= 3 and nn not in out:
            out.append(nn)
    return out


def match_identities(session: Session, text: str) -> list[IdentityMatch]:
    norm = normalize_name(text or "")
    if not norm:
        return []
    matches: list[IdentityMatch] = []
    for ident in session.scalars(select(Identity)).all():
        best: IdentityMatch | None = None
        for name in identity_names(ident):
            if contains_word(norm, name):
                # longer names are stronger evidence than short aliases/initials
                score = min(1.0, 0.6 + 0.05 * len(name.split()) + 0.01 * len(name))
                if best is None or score > best.score:
                    best = IdentityMatch(ident.id, name, round(score, 2))
        if best:
            matches.append(best)
    return sorted(matches, key=lambda m: -m.score)


def resolve_account_owners(
    session: Session, account: Account, holder_text: str | None, header_text: str | None
) -> list[IdentityMatch]:
    """Attach owners inferred from document evidence. User-set owners are authoritative."""
    if any(o.source == "user" for o in account.owners):
        return []
    found = match_identities(session, holder_text or "") if holder_text else []
    source = "document_header"
    if not found:
        found = match_identities(session, header_text or "")
        found = [IdentityMatch(m.identity_id, m.matched, round(m.score * 0.85, 2)) for m in found]
        source = "alias_match"
    existing = {o.identity_id for o in account.owners}
    for m in found:
        if m.identity_id not in existing:
            account.owners.append(
                AccountOwner(identity_id=m.identity_id, source=source, confidence=m.score)
            )
    session.flush()
    return found


def account_owner_ids(account: Account) -> list[int]:
    return [o.identity_id for o in account.owners]
