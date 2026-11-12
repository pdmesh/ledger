"""Reconciliation: internal transfers, card settlements, refunds and duplicates.

Reconciliation *relates* transactions; it never deletes them. Analytics use the links
(via categories/roles and ``duplicate_of_id``) to avoid double counting while the ledger
keeps every original movement.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ledger.config import current_version, get_setting
from ledger.intelligence.router import IntelligenceRouter, NoProviderAvailable, ProviderFactory
from ledger.intelligence.tasks import adjudicate_match
from ledger.models import (
    Account,
    Category,
    ClassificationRecord,
    ReconciliationLink,
    Transaction,
    utcnow,
)
from ledger.text import contains_word, jaccard, normalize_description

log = logging.getLogger(__name__)

TRANSFER_CUES = (
    "transfer",
    "trf",
    "neft",
    "imps",
    "rtgs",
    "self",
    "own account",
    "own a/c",
    "fund transfer",
    "ft",
    "sweep",
    "zelle",
    "faster payment",
    "bacs",
    "giro",
)
CARD_CUES = (
    "credit card",
    "card payment",
    "cc payment",
    "ccpay",
    "card bill",
    "autopay",
    "bbps",
    "card no",
    "creditcard",
)
REFUND_CUES = ("refund", "reversal", "reversed", "chargeback", "return", "cancel")
LINK_THRESHOLD = 0.7
AMBIGUITY_MARGIN = 0.05


@dataclass
class Candidate:
    txn: Transaction
    score: float
    evidence: dict[str, Any] = field(default_factory=dict)


def _amt(t: Transaction) -> Decimal:
    return abs(Decimal(t.amount))


def _has_cue(t: Transaction, cues: Iterable[str]) -> list[str]:
    norm = t.description_normalized or normalize_description(t.description_raw)
    return [c for c in cues if contains_word(norm, c)]


class Reconciler:
    def __init__(
        self,
        session: Session,
        *,
        provider_factory: ProviderFactory | None = None,
        use_ai: bool = True,
    ):
        self.session = session
        self.pf = provider_factory
        self.use_ai = use_ai
        self.cfg = get_setting(session, "reconciliation")
        self.cats = {c.slug: c for c in session.scalars(select(Category)).all()}
        self.cats_by_id = {c.id: c for c in self.cats.values()}
        self.accounts = {a.id: a for a in session.scalars(select(Account)).all()}
        self.config_version = current_version(session)
        self.ai_available = use_ai and IntelligenceRouter(session, provider_factory).available(
            "reconcile"
        )

    # -- loading -------------------------------------------------------------------------

    def _load(self, date_from: date | None, date_to: date | None) -> list[Transaction]:
        pad = max(
            int(self.cfg["transfer_window_days"]),
            int(self.cfg["settlement_window_days"]),
            int(self.cfg["refund_window_days"]),
        )
        q = select(Transaction).where(Transaction.duplicate_of_id.is_(None))
        if date_from:
            q = q.where(Transaction.txn_date >= date_from - timedelta(days=pad))
        if date_to:
            q = q.where(Transaction.txn_date <= date_to + timedelta(days=pad))
        return list(self.session.scalars(q.order_by(Transaction.txn_date, Transaction.id)).all())

    def _existing_pairs(self, ids: set[int]) -> tuple[set[tuple[str, int, int]], set[int]]:
        """(kind, from, to) for every link (any status) and ids already actively linked."""
        links = self.session.scalars(
            select(ReconciliationLink).where(
                or_(
                    ReconciliationLink.from_transaction_id.in_(ids),
                    ReconciliationLink.to_transaction_id.in_(ids),
                )
            )
        ).all()
        pairs = {(lk.kind, lk.from_transaction_id, lk.to_transaction_id) for lk in links}
        active = set()
        for lk in links:
            if lk.status != "rejected" and lk.kind in ("internal_transfer", "card_settlement"):
                active.add(lk.from_transaction_id)
                active.add(lk.to_transaction_id)
        return pairs, active

    def _role(self, t: Transaction) -> str | None:
        c = self.cats_by_id.get(t.category_id) if t.category_id else None
        return c.role if c else None

    def _strongly_non_transfer(self, t: Transaction) -> bool:
        """True when the user or a strong deterministic signal says it's not a transfer."""
        pinned = "category" in (t.pinned_fields or [])
        role = self._role(t)
        if pinned and role != "transfer":
            return True
        return (
            t.classification_method in ("merchant_map", "rule")
            and role in ("income", "investment", "expense")
            and (t.classification_confidence or 0) >= 0.85
        )

    # -- main ----------------------------------------------------------------------------

    def run(self, date_from: date | None = None, date_to: date | None = None) -> dict[str, int]:
        txns = self._load(date_from, date_to)
        if not txns:
            return {}
        ids = {t.id for t in txns}
        pairs, active = self._existing_pairs(ids)
        stats = {
            "duplicates": 0,
            "card_settlements": 0,
            "internal_transfers": 0,
            "refunds": 0,
            "ambiguous": 0,
        }
        stats["duplicates"] = self._duplicates(txns, pairs)
        txns = [t for t in txns if t.duplicate_of_id is None]
        stats["card_settlements"] = self._pairs(txns, pairs, active, "card_settlement", stats)
        stats["internal_transfers"] = self._pairs(txns, pairs, active, "internal_transfer", stats)
        stats["refunds"] = self._refunds(txns, pairs)
        self.session.flush()
        return stats

    # -- duplicates across documents/formats ---------------------------------------------

    def _duplicates(self, txns: list[Transaction], pairs: set[tuple[str, int, int]]) -> int:
        threshold = float(self.cfg["duplicate_min_confidence"])
        by_key: dict[tuple[int, Decimal], list[Transaction]] = {}
        for t in txns:
            by_key.setdefault((t.account_id, Decimal(t.amount)), []).append(t)
        n = 0
        for group in by_key.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda t: t.id)
            for i, a in enumerate(group):
                if a.duplicate_of_id:
                    continue
                for b in group[i + 1 :]:
                    if b.duplicate_of_id or b.document_id == a.document_id:
                        continue
                    if a.document_id is None or b.document_id is None:
                        continue
                    days = abs((a.txn_date - b.txn_date).days)
                    if days > 1:
                        continue
                    sim = jaccard(a.description_raw, b.description_raw)
                    same_ref = bool(a.reference and a.reference == b.reference)
                    if sim < 0.3 and not same_ref:
                        continue
                    conf = min(
                        0.99,
                        0.55 + 0.35 * sim + (0.1 if days == 0 else 0) + (0.2 if same_ref else 0),
                    )
                    if ("duplicate", a.id, b.id) in pairs:
                        continue
                    applied = conf >= threshold
                    self._link(
                        "duplicate",
                        a,
                        b,
                        conf,
                        "deterministic",
                        {
                            "description_similarity": round(sim, 2),
                            "day_diff": days,
                            "same_reference": same_ref,
                            "applied": applied,
                        },
                    )
                    pairs.add(("duplicate", a.id, b.id))
                    if applied and "duplicate" not in (b.pinned_fields or []):
                        b.duplicate_of_id = a.id
                        n += 1
                        break
        return n

    # -- transfers & card settlements ----------------------------------------------------

    def _pairs(
        self,
        txns: list[Transaction],
        pairs: set[tuple[str, int, int]],
        active: set[int],
        kind: str,
        stats: dict[str, int],
    ) -> int:
        window = int(
            self.cfg[
                "settlement_window_days" if kind == "card_settlement" else "transfer_window_days"
            ]
        )
        bank_types = {"savings", "current", "cash", "other"}

        def eligible_out(t: Transaction) -> bool:
            a = self.accounts[t.account_id]
            if t.direction != "outflow" or t.id in active:
                return False
            if kind == "card_settlement":
                return a.account_type in bank_types
            return a.account_type not in ("credit_card",)

        def eligible_in(t: Transaction) -> bool:
            a = self.accounts[t.account_id]
            if t.direction != "inflow" or t.id in active:
                return False
            if kind == "card_settlement":
                return a.account_type == "credit_card"
            return a.account_type not in ("credit_card",)

        outs = [t for t in txns if eligible_out(t)]
        ins_by_amt: dict[tuple[str, Decimal], list[Transaction]] = {}
        for t in txns:
            if eligible_in(t):
                ins_by_amt.setdefault((t.currency, _amt(t)), []).append(t)

        linked = 0
        for o in outs:
            if o.id in active:
                continue
            cands: list[Candidate] = []
            for i in ins_by_amt.get((o.currency, _amt(o)), []):
                if i.id in active or i.account_id == o.account_id:
                    continue
                if (kind, o.id, i.id) in pairs:
                    continue  # previously decided (incl. rejected by the user)
                delta = (i.txn_date - o.txn_date).days
                lo = -2 if kind == "card_settlement" else -window
                if delta < lo or delta > window:
                    continue
                c = self._score(kind, o, i, abs(delta), window)
                if c:
                    cands.append(c)
            if not cands:
                continue
            cands.sort(key=lambda c: -c.score)
            best = cands[0]
            method = "deterministic"
            if len(cands) > 1 and cands[1].score >= best.score - AMBIGUITY_MARGIN:
                stats["ambiguous"] += 1
                chosen = self._adjudicate(kind, o, cands)
                if chosen is None:
                    continue
                best, method = chosen, "llm" if chosen.evidence.get("adjudicated") else method
            if best.score < LINK_THRESHOLD:
                continue
            self._link(kind, o, best.txn, best.score, method, best.evidence)
            pairs.add((kind, o.id, best.txn.id))
            active.update({o.id, best.txn.id})
            slug = "card-settlement" if kind == "card_settlement" else "internal-transfer"
            for t in (o, best.txn):
                self._set_category(t, slug, best.score, {"link": kind})
            linked += 1
        return linked

    def _score(
        self, kind: str, o: Transaction, i: Transaction, days: int, window: int
    ) -> Candidate | None:
        ev: dict[str, Any] = {"amount_match": True, "day_diff": days}
        score = 0.55 + 0.15 * (1 - days / max(window, 1))
        in_acct = self.accounts[i.account_id]
        out_acct = self.accounts[o.account_id]
        if kind == "card_settlement":
            cues = _has_cue(o, CARD_CUES) + _has_cue(i, ("payment", "thank you", "received"))
            if in_acct.masked_number and in_acct.masked_number in o.description_raw:
                score += 0.2
                ev["card_number_in_description"] = True
            inst = in_acct.institution.name.lower() if in_acct.institution else None
            if inst and contains_word(o.description_normalized, inst.split()[0]):
                score += 0.05
                ev["card_institution_in_description"] = True
        else:
            if self._strongly_non_transfer(o) or self._strongly_non_transfer(i):
                # e.g. salary inflow coincidentally equal to a rent outflow
                if not (_has_cue(o, TRANSFER_CUES) and _has_cue(i, TRANSFER_CUES)):
                    return None
            cues = _has_cue(o, TRANSFER_CUES) + _has_cue(i, TRANSFER_CUES)
            for a, t in ((in_acct, o), (out_acct, i)):
                if a.masked_number and a.masked_number in t.description_raw:
                    score += 0.15
                    ev["counterpart_account_in_description"] = True
            if o.reference and o.reference == i.reference:
                score += 0.2
                ev["same_reference"] = True
            owners_in = {ow.identity_id for ow in in_acct.owners}
            owners_out = {ow.identity_id for ow in out_acct.owners}
            ev["same_owner"] = bool(owners_in & owners_out)
            ev["between_household_members"] = bool(owners_in and owners_out) and not (
                owners_in & owners_out
            )
        if cues:
            score += min(0.15, 0.08 * len(set(cues)))
            ev["cues"] = sorted(set(cues))
        return Candidate(i, round(min(score, 0.99), 3), ev)

    def _adjudicate(self, kind: str, o: Transaction, cands: list[Candidate]) -> Candidate | None:
        top = cands[:5]
        if self.ai_available:
            try:
                cid, conf, reason = adjudicate_match(
                    self.session,
                    kind,
                    {
                        "id": o.id,
                        "date": o.txn_date,
                        "description": o.description_raw,
                        "amount": str(o.amount),
                        "account": self.accounts[o.account_id].name,
                    },
                    [
                        {
                            "id": c.txn.id,
                            "date": c.txn.txn_date,
                            "description": c.txn.description_raw,
                            "amount": str(c.txn.amount),
                            "account": self.accounts[c.txn.account_id].name,
                            "deterministic_score": c.score,
                        }
                        for c in top
                    ],
                    provider_factory=self.pf,
                )
                if cid is None:
                    return None
                chosen = next(c for c in top if c.txn.id == cid)
                chosen.score = round(min(0.99, max(chosen.score, conf)), 3)
                chosen.evidence = {**chosen.evidence, "adjudicated": True, "reason": reason}
                return chosen
            except (NoProviderAvailable, StopIteration):
                pass
        # deterministic tie-break: closest date, then lowest id; confidence reduced
        best = sorted(top, key=lambda c: (-c.score, c.evidence.get("day_diff", 99), c.txn.id))[0]
        best.score = round(best.score * 0.9, 3)
        best.evidence = {**best.evidence, "ambiguous_candidates": [c.txn.id for c in top]}
        return best

    # -- refunds -------------------------------------------------------------------------

    def _refunds(self, txns: list[Transaction], pairs: set[tuple[str, int, int]]) -> int:
        window = int(self.cfg["refund_window_days"])
        already = {p[2] for p in pairs if p[0] == "refund"}
        outs_by_merchant: dict[int, list[Transaction]] = {}
        for t in txns:
            if t.direction == "outflow" and t.merchant_id:
                outs_by_merchant.setdefault(t.merchant_id, []).append(t)
        n = 0
        for r in txns:
            if r.direction != "inflow" or r.id in already or not r.merchant_id:
                continue
            role = self._role(r)
            cues = _has_cue(r, REFUND_CUES)
            if role not in ("adjustment", "expense", None) and not cues:
                continue
            if role != "adjustment" and not cues and self._role_is_strong(r):
                continue
            best: Candidate | None = None
            for o in outs_by_merchant.get(r.merchant_id, []):
                days = (r.txn_date - o.txn_date).days
                if days < 0 or days > window or _amt(r) > _amt(o):
                    continue
                if o.currency != r.currency:
                    continue
                score = 0.5 + (0.25 if _amt(r) == _amt(o) else 0.05)
                score += 0.1 if o.account_id == r.account_id else 0
                score += 0.1 * (1 - days / window)
                score += 0.05 if cues else 0
                if best is None or score > best.score:
                    best = Candidate(
                        o,
                        round(score, 3),
                        {
                            "same_merchant": True,
                            "exact_amount": _amt(r) == _amt(o),
                            "day_diff": days,
                            "cues": cues,
                        },
                    )
            if best and best.score >= LINK_THRESHOLD:
                self._link("refund", best.txn, r, best.score, "deterministic", best.evidence)
                pairs.add(("refund", best.txn.id, r.id))
                if role != "adjustment":
                    self._set_category(r, "refund", best.score, {"link": "refund"})
                n += 1
        return n

    def _role_is_strong(self, t: Transaction) -> bool:
        return "category" in (t.pinned_fields or []) or t.classification_method in (
            "merchant_map",
            "rule",
        )

    # -- mutation helpers ----------------------------------------------------------------

    def _link(
        self,
        kind: str,
        a: Transaction,
        b: Transaction,
        conf: float,
        method: str,
        evidence: dict[str, Any],
    ) -> ReconciliationLink:
        lk = ReconciliationLink(
            kind=kind,
            from_transaction_id=a.id,
            to_transaction_id=b.id,
            confidence=round(conf, 3),
            method=method,
            evidence=evidence,
            status="auto",
            history=[
                {
                    "at": utcnow().isoformat(),
                    "action": "created",
                    "method": method,
                    "confidence": round(conf, 3),
                    "config_version": self.config_version,
                }
            ],
        )
        self.session.add(lk)
        self.session.flush()
        return lk

    def _set_category(self, t: Transaction, slug: str, conf: float, ev: dict[str, Any]) -> None:
        if "category" in (t.pinned_fields or []) or slug not in self.cats:
            return
        cat = self.cats[slug]
        if t.category_id == cat.id and t.classification_method == "reconciliation":
            return
        t.category_id = cat.id
        t.classification_method = "reconciliation"
        t.classification_confidence = conf
        t.classification_evidence = ev
        t.classification_config_version = self.config_version
        self.session.add(
            ClassificationRecord(
                transaction_id=t.id,
                method="reconciliation",
                category_id=cat.id,
                merchant_id=t.merchant_id,
                confidence=conf,
                evidence=ev,
                config_version=self.config_version,
            )
        )


def set_link_status(session: Session, link_id: int, status: str, note: str | None = None) -> None:
    """User confirmation/rejection. Rejection restores independent classification."""
    from ledger.classification.engine import Classifier

    lk = session.get(ReconciliationLink, link_id)
    if lk is None:
        raise ValueError("link not found")
    if status not in ("confirmed", "rejected", "auto"):
        raise ValueError("invalid status")
    lk.status = status
    lk.method = "user" if status != "auto" else lk.method
    lk.history = [*(lk.history or []), {"at": utcnow().isoformat(), "action": status, "note": note}]
    a = session.get(Transaction, lk.from_transaction_id)
    b = session.get(Transaction, lk.to_transaction_id)
    if status == "rejected":
        if lk.kind == "duplicate" and b and b.duplicate_of_id == a.id:
            b.duplicate_of_id = None
        affected = [t for t in (a, b) if t and t.classification_method == "reconciliation"]
        for t in affected:
            t.category_id = None
            t.classification_method = None
        session.flush()
        if affected:
            Classifier(session).classify(affected)
    elif status == "confirmed" and lk.kind == "duplicate" and b and a:
        b.duplicate_of_id = a.id
    session.flush()
