"""Merchant normalization: map messy descriptions onto canonical merchant entities."""

from __future__ import annotations

import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ledger.models import Merchant, MerchantAlias, Transaction
from ledger.text import contains_word, merchant_key, normalize_description, slugify


class MerchantResolver:
    """In-memory alias index for fast resolution during a processing run."""

    def __init__(self, session: Session):
        self.session = session
        self.reload()

    def reload(self) -> None:
        self.by_key: dict[str, int] = {}
        self.contains: list[tuple[str, int, bool]] = []  # (pattern, merchant_id, is_user)
        self.regex: list[tuple[re.Pattern[str], int, bool]] = []
        merchants = self.session.scalars(select(Merchant)).all()
        self.merchants = {m.id: m for m in merchants}
        for m in merchants:
            self.by_key.setdefault(m.key, m.id)
        for a in self.session.scalars(select(MerchantAlias)).all():
            user = a.source == "user"
            if a.match_type == "key":
                if user or a.pattern not in self.by_key:
                    self.by_key[a.pattern] = a.merchant_id
            elif a.match_type == "contains":
                self.contains.append((a.pattern, a.merchant_id, user))
            elif a.match_type == "regex":
                try:
                    self.regex.append((re.compile(a.pattern, re.I), a.merchant_id, user))
                except re.error:
                    continue
        # user-defined patterns first, longer patterns before shorter ones
        self.contains.sort(key=lambda x: (not x[2], -len(x[0])))
        self.regex.sort(key=lambda x: not x[1])

    def resolve(self, description: str, *, create: bool = True) -> tuple[Merchant | None, str]:
        """Return (merchant, method). Method: alias|key|created|none."""
        norm = normalize_description(description)
        for pattern, mid, _ in self.contains:
            if contains_word(norm, pattern):
                return self.merchants[mid], "alias"
        for rx, mid, _ in self.regex:
            if rx.search(description):
                return self.merchants[mid], "alias"
        key = merchant_key(description)
        if not key:
            return None, "none"
        if key in self.by_key:
            return self.merchants[self.by_key[key]], "key"
        if not create:
            return None, "none"
        m = Merchant(canonical_name=key.title(), key=key, source="auto")
        self.session.add(m)
        self.session.flush()
        self.session.add(MerchantAlias(merchant_id=m.id, pattern=key, match_type="key"))
        self.merchants[m.id] = m
        self.by_key[key] = m.id
        return m, "created"


def merge_merchants(session: Session, source_id: int, target_id: int) -> int:
    """Merge ``source`` into ``target``: move aliases and transactions. Returns txn count."""
    if source_id == target_id:
        return 0
    src = session.get(Merchant, source_id)
    tgt = session.get(Merchant, target_id)
    if not src or not tgt:
        raise ValueError("merchant not found")
    for a in list(src.aliases):
        exists = session.scalar(
            select(MerchantAlias).where(
                MerchantAlias.merchant_id == tgt.id,
                MerchantAlias.pattern == a.pattern,
                MerchantAlias.match_type == a.match_type,
            )
        )
        if exists:
            session.delete(a)
        else:
            a.merchant_id = tgt.id
    # keep the old canonical key resolvable
    session.flush()
    n = session.execute(
        update(Transaction).where(Transaction.merchant_id == src.id).values(merchant_id=tgt.id)
    ).rowcount
    if tgt.default_category_id is None:
        tgt.default_category_id = src.default_category_id
    old_key = src.key
    session.delete(src)
    session.flush()
    if not session.scalar(
        select(MerchantAlias).where(
            MerchantAlias.pattern == old_key, MerchantAlias.match_type == "key"
        )
    ):
        session.add(
            MerchantAlias(merchant_id=tgt.id, pattern=old_key, match_type="key", source="user")
        )
    return n or 0


def find_or_create_named(session: Session, name: str, source: str = "llm") -> Merchant:
    key = slugify(name).replace("-", " ")
    m = session.scalar(select(Merchant).where(Merchant.key == key))
    if m:
        return m
    m = Merchant(canonical_name=name, key=key, source=source)
    session.add(m)
    session.flush()
    return m
