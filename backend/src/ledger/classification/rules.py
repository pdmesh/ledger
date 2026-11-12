"""Deterministic classification rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger.models import ClassificationRule, Transaction
from ledger.text import contains_word, normalize_description


@dataclass
class CompiledRule:
    rule: ClassificationRule
    words: list[str]
    regex: re.Pattern[str] | None

    def matches(self, txn: Transaction, account_type: str) -> bool:
        c: dict[str, Any] = self.rule.conditions or {}
        norm = txn.description_normalized or normalize_description(txn.description_raw)
        if self.words and not any(contains_word(norm, w) for w in self.words):
            return False
        if self.regex and not self.regex.search(txn.description_raw):
            return False
        if c.get("direction") and c["direction"] != txn.direction:
            return False
        if c.get("account_ids") and txn.account_id not in c["account_ids"]:
            return False
        if c.get("account_types") and account_type not in c["account_types"]:
            return False
        if c.get("merchant_ids") and txn.merchant_id not in c["merchant_ids"]:
            return False
        amt = abs(Decimal(txn.amount))
        if c.get("min_amount") is not None and amt < Decimal(str(c["min_amount"])):
            return False
        if c.get("max_amount") is not None and amt > Decimal(str(c["max_amount"])):
            return False
        has_condition = any(
            c.get(k)
            for k in ("description_contains", "description_regex", "account_ids", "merchant_ids")
        )
        return has_condition


def load_rules(session: Session) -> list[CompiledRule]:
    rules = session.scalars(
        select(ClassificationRule).where(ClassificationRule.active.is_(True))
    ).all()
    # user and learned rules precede shipped system rules
    rules = sorted(rules, key=lambda r: (r.source == "system", r.priority, r.id))
    out = []
    for r in rules:
        c = r.conditions or {}
        rx = None
        if c.get("description_regex"):
            try:
                rx = re.compile(c["description_regex"], re.I)
            except re.error:
                continue
        words = [w.lower() for w in c.get("description_contains", []) if w]
        out.append(CompiledRule(r, words, rx))
    return out
