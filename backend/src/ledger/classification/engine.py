"""Autonomous classification with a strict precedence chain.

1. User overrides (pinned fields) -- never touched.
2. Reconciliation decisions (transfer / settlement links) -- kept while the link stands.
3. User merchant mappings (merchant default category, source=user).
4. Deterministic rules (user/learned first, then shipped system rules).
5. Historical patterns (user corrections for the same merchant; earlier AI decisions).
6. LLM interpretation (batched, only for what is left, only if a provider is routed).
7. Fallback category by direction.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger import defaults
from ledger.classification.merchants import MerchantResolver, find_or_create_named
from ledger.classification.rules import load_rules
from ledger.config import current_version, get_setting
from ledger.intelligence.router import NoProviderAvailable, ProviderFactory
from ledger.intelligence.tasks import TxnForAI, classify_transactions
from ledger.models import Category, ClassificationRecord, Merchant, Transaction
from ledger.text import merchant_key, normalize_description

log = logging.getLogger(__name__)


@dataclass
class Decision:
    category_id: int
    method: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    ai_execution_id: int | None = None


@dataclass
class ClassifyStats:
    processed: int = 0
    by_method: Counter[str] = field(default_factory=Counter)
    ai_calls: int = 0
    ai_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "by_method": dict(self.by_method),
            "ai_calls": self.ai_calls,
            "ai_errors": self.ai_errors[:5],
        }


class Classifier:
    def __init__(
        self,
        session: Session,
        *,
        use_ai: bool = True,
        provider_factory: ProviderFactory | None = None,
    ):
        self.session = session
        self.use_ai = use_ai
        self.provider_factory = provider_factory
        self.cats = {c.slug: c for c in session.scalars(select(Category)).all()}
        self.cats_by_id = {c.id: c for c in self.cats.values()}
        self.rules = load_rules(session)
        self.merchants = MerchantResolver(session)
        self.config_version = current_version(session)
        self.batch_size = int(get_setting(session, "intelligence").get("batch_size", 40))
        self._history = self._load_history()

    # -- helpers -------------------------------------------------------------------------

    def _active_category(self, cid: int | None) -> Category | None:
        seen = 0
        c = self.cats_by_id.get(cid) if cid else None
        while c is not None and not c.active and c.merged_into_id and seen < 10:
            c = self.cats_by_id.get(c.merged_into_id)
            seen += 1
        return c if c is not None and c.active else None

    def _load_history(self) -> dict[int, Counter[int]]:
        """merchant_id -> Counter(category_id) from user-pinned categories."""
        hist: dict[int, Counter[int]] = defaultdict(Counter)
        rows = self.session.execute(
            select(
                Transaction.merchant_id, Transaction.category_id, Transaction.pinned_fields
            ).where(Transaction.merchant_id.is_not(None), Transaction.category_id.is_not(None))
        ).all()
        for mid, cid, pinned in rows:
            if pinned and "category" in pinned:
                hist[mid][cid] += 1
        return hist

    def _fallback(self, txn: Transaction, account_type: str) -> Decision:
        if txn.direction == "outflow":
            slug = defaults.FALLBACK_OUTFLOW
        elif account_type == "credit_card":
            slug = "refund"
        else:
            slug = defaults.FALLBACK_INFLOW
        cat = self.cats.get(slug) or next(iter(self.cats.values()))
        return Decision(cat.id, "fallback", 0.2, {"reason": "no rule, mapping or model result"})

    def _adjust_for_direction(self, cat: Category, txn: Transaction) -> tuple[Category, str | None]:
        """An inflow from a merchant mapped to an expense category is most likely a refund."""
        if cat.role == "expense" and txn.direction == "inflow" and "refund" in self.cats:
            return self.cats["refund"], "inflow from expense merchant treated as refund"
        return cat, None

    # -- deterministic layers ------------------------------------------------------------

    def _deterministic(self, txn: Transaction, account_type: str) -> Decision | None:
        m: Merchant | None = self.merchants.merchants.get(txn.merchant_id or -1)
        if m and m.source == "user" and m.default_category_id:
            cat = self._active_category(m.default_category_id)
            if cat:
                cat, note = self._adjust_for_direction(cat, txn)
                ev = {"merchant": m.canonical_name}
                if note:
                    ev["note"] = note
                return Decision(cat.id, "merchant_map", 0.95, ev)

        for cr in self.rules:
            if cr.matches(txn, account_type):
                slug = (cr.rule.actions or {}).get("category")
                cat = self._active_category(self.cats[slug].id) if slug in self.cats else None
                if cat:
                    if (cr.rule.actions or {}).get("owner_identity_id") and "owner" not in (
                        txn.pinned_fields or []
                    ):
                        txn.owner_identity_id = cr.rule.actions["owner_identity_id"]
                    return Decision(
                        cat.id,
                        "rule",
                        float(cr.rule.confidence),
                        {"rule_id": cr.rule.id, "rule": cr.rule.name},
                    )

        if m:
            counts = self._history.get(m.id)
            if counts:
                cid, n = counts.most_common(1)[0]
                cat = self._active_category(cid)
                if cat:
                    cat, note = self._adjust_for_direction(cat, txn)
                    total = sum(counts.values())
                    return Decision(
                        cat.id,
                        "history",
                        round(0.6 + 0.35 * n / total, 2),
                        {"merchant": m.canonical_name, "corrections": n},
                    )
            if m.default_category_id and m.source in ("llm", "auto"):
                cat = self._active_category(m.default_category_id)
                if cat:
                    cat, note = self._adjust_for_direction(cat, txn)
                    return Decision(
                        cat.id,
                        "history",
                        0.7,
                        {"merchant": m.canonical_name, "from": "earlier AI decision"},
                    )
        return None

    # -- main entry ----------------------------------------------------------------------

    def classify(
        self, txns: list[Transaction], *, force: bool = False, deterministic_only: bool = False
    ) -> ClassifyStats:
        """Classify ``txns``.

        ``force`` recomputes already-classified rows (except user pins and reconciliation).
        ``deterministic_only`` never calls a model and keeps an existing classification
        when no deterministic layer matches -- used when propagating rule/mapping changes
        so that configuration edits don't trigger unnecessary LLM calls.
        """
        stats = ClassifyStats()
        accounts = {t.account_id: t.account.account_type for t in txns}
        pending_ai: list[Transaction] = []

        for txn in txns:
            if txn.duplicate_of_id:
                continue
            stats.processed += 1
            pinned = set(txn.pinned_fields or [])
            if not txn.description_normalized:
                txn.description_normalized = normalize_description(txn.description_raw)
            if "merchant" not in pinned and (force or txn.merchant_id is None):
                m, _ = self.merchants.resolve(txn.description_raw)
                txn.merchant_id = m.id if m else None
            if "category" in pinned:
                stats.by_method["user"] += 1
                continue
            if txn.classification_method == "reconciliation":
                stats.by_method["reconciliation"] += 1
                continue
            if not force and txn.category_id is not None:
                continue  # incremental run: only classify what has no category yet
            d = self._deterministic(txn, accounts[txn.account_id])
            if d:
                self._apply(txn, d)
                stats.by_method[d.method] += 1
            else:
                pending_ai.append(txn)

        ai_done: set[int] = set()
        if deterministic_only:
            active_rules = {cr.rule.id for cr in self.rules}

            def still_valid(t: Transaction) -> bool:
                if t.category_id is None:
                    return False
                rid = (t.classification_evidence or {}).get("rule_id")
                return not (t.classification_method == "rule" and rid not in active_rules)

            ai_done = {t.id for t in pending_ai if still_valid(t)}
        elif pending_ai and self.use_ai:
            ai_done = self._classify_with_ai(pending_ai, accounts, stats)
        for txn in pending_ai:
            if txn.id not in ai_done:
                d = self._fallback(txn, accounts[txn.account_id])
                self._apply(txn, d)
                stats.by_method["fallback"] += 1
        self.session.flush()
        return stats

    def _classify_with_ai(
        self, txns: list[Transaction], accounts: dict[int, str], stats: ClassifyStats
    ) -> set[int]:
        done: set[int] = set()
        for i in range(0, len(txns), self.batch_size):
            batch = txns[i : i + self.batch_size]
            items = [
                TxnForAI(
                    ref=t.id,
                    description=t.description_raw,
                    amount=Decimal(t.amount),
                    currency=t.currency,
                    direction=t.direction,
                    account_type=accounts[t.account_id],
                    txn_date=t.txn_date,
                    merchant_hint=merchant_key(t.description_raw) or None,
                )
                for t in batch
            ]
            try:
                results, exec_id = classify_transactions(
                    self.session, items, provider_factory=self.provider_factory
                )
                stats.ai_calls += 1
            except NoProviderAvailable as e:
                if "all providers failed" in str(e):
                    stats.ai_errors.append(str(e))
                return done  # no provider: deterministic fallback handles the rest
            by_ref = {r.ref: r for r in results}
            for t in batch:
                r = by_ref.get(t.id)
                if not r:
                    continue
                cat = self.cats[r.category]
                if r.merchant and "merchant" not in (t.pinned_fields or []):
                    self._apply_ai_merchant(t, r.merchant, cat)
                t.is_recurring = t.is_recurring or r.recurring
                self._apply(
                    t,
                    Decision(
                        cat.id, "llm", r.confidence, {"reason": r.reason}, ai_execution_id=exec_id
                    ),
                )
                done.add(t.id)
                stats.by_method["llm"] += 1
        return done

    def _apply_ai_merchant(self, txn: Transaction, name: str, cat: Category) -> None:
        current = self.merchants.merchants.get(txn.merchant_id or -1)
        if current and current.source == "user":
            return
        target = find_or_create_named(self.session, name)
        self.merchants.merchants[target.id] = target
        if current and current.source == "auto" and current.id != target.id:
            # normalize: the auto key now resolves to the AI-named canonical merchant
            from ledger.classification.merchants import merge_merchants

            merge_merchants(self.session, current.id, target.id)
            self.merchants.reload()
        txn.merchant_id = target.id
        if target.default_category_id is None and cat.role in ("expense", "income"):
            target.default_category_id = cat.id

    def _apply(self, txn: Transaction, d: Decision) -> None:
        changed = txn.category_id != d.category_id or txn.classification_method != d.method
        txn.category_id = d.category_id
        txn.classification_method = d.method
        txn.classification_confidence = d.confidence
        txn.classification_evidence = d.evidence
        txn.classification_config_version = self.config_version
        if changed:
            self.session.add(
                ClassificationRecord(
                    transaction_id=txn.id,
                    method=d.method,
                    category_id=d.category_id,
                    merchant_id=txn.merchant_id,
                    confidence=d.confidence,
                    evidence=d.evidence,
                    ai_execution_id=d.ai_execution_id,
                    config_version=self.config_version,
                )
            )


def detect_recurring(session: Session, merchant_ids: set[int] | None = None) -> int:
    """Flag transactions from merchants charging similar amounts in 3+ distinct months."""
    q = select(Transaction).where(
        Transaction.merchant_id.is_not(None), Transaction.duplicate_of_id.is_(None)
    )
    if merchant_ids:
        q = q.where(Transaction.merchant_id.in_(merchant_ids))
    groups: dict[tuple[int, int, str], list[Transaction]] = defaultdict(list)
    for t in session.scalars(q).all():
        groups[(t.merchant_id, t.account_id, t.direction)].append(t)
    flagged = 0
    for txns in groups.values():
        months = {(t.txn_date.year, t.txn_date.month) for t in txns}
        if len(months) < 3:
            continue
        amounts = sorted(abs(Decimal(t.amount)) for t in txns)
        median = amounts[len(amounts) // 2]
        for t in txns:
            similar = median and abs(abs(Decimal(t.amount)) - median) <= median * Decimal("0.15")
            if similar and not t.is_recurring:
                t.is_recurring = True
                flagged += 1
    session.flush()
    return flagged
