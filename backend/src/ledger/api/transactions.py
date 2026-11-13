"""Transaction explorer, details, corrections, manual entry and reconciliation links."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ledger.analytics.service import Filters, apply_filters
from ledger.api import serializers as ser
from ledger.api.deps import bad_request, get_session, not_found, notify_worker
from ledger.classification.engine import Classifier
from ledger.fx import apply_base_amount, base_currency
from ledger.jobs import enqueue
from ledger.models import (
    Account,
    AIExecution,
    Category,
    ClassificationRecord,
    Document,
    ReconciliationLink,
    Transaction,
    TransactionOverride,
)
from ledger.propagation import apply_override
from ledger.reconciliation.engine import set_link_status
from ledger.text import normalize_description

router = APIRouter(tags=["transactions"])

SORTS = {
    "date": Transaction.txn_date,
    "amount": Transaction.base_amount,
    "confidence": Transaction.classification_confidence,
}


@router.get("/transactions")
def list_transactions(
    s: Session = Depends(get_session),
    date_from: date | None = None,
    date_to: date | None = None,
    identity_id: int | None = None,
    scope: str = "household",
    account_id: list[int] = Query(default=[]),
    institution_id: list[int] = Query(default=[]),
    category_id: list[int] = Query(default=[]),
    merchant_id: list[int] = Query(default=[]),
    role: list[str] = Query(default=[]),
    direction: str | None = None,
    currency: str | None = None,
    reconciliation: str | None = None,  # linked|unlinked|duplicate
    method: list[str] = Query(default=[]),
    document_id: list[int] = Query(default=[]),
    max_confidence: float | None = None,
    recurring: bool | None = None,
    q: str | None = None,
    include_duplicates: bool = False,
    sort: str = "date",
    order: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    f = Filters(
        date_from,
        date_to,
        identity_id,
        scope,
        account_id,
        institution_id,
        currency,
        include_duplicates=include_duplicates or reconciliation == "duplicate",
    )
    query = select(Transaction).outerjoin(Category, Category.id == Transaction.category_id)
    query = apply_filters(query, f, s)
    if reconciliation == "duplicate":
        query = query.where(Transaction.duplicate_of_id.is_not(None))
    if category_id:
        query = query.where(Transaction.category_id.in_(category_id))
    if merchant_id:
        query = query.where(Transaction.merchant_id.in_(merchant_id))
    if role:
        query = query.where(Category.role.in_(role))
    if direction in ("inflow", "outflow"):
        query = query.where(Transaction.direction == direction)
    if method:
        query = query.where(Transaction.classification_method.in_(method))
    if document_id:
        query = query.where(Transaction.document_id.in_(document_id))
    if max_confidence is not None:
        query = query.where(Transaction.classification_confidence <= max_confidence)
    if recurring is not None:
        query = query.where(Transaction.is_recurring.is_(recurring))
    if reconciliation in ("linked", "unlinked"):
        linked = (
            select(ReconciliationLink.from_transaction_id)
            .where(ReconciliationLink.status != "rejected")
            .union(
                select(ReconciliationLink.to_transaction_id).where(
                    ReconciliationLink.status != "rejected"
                )
            )
        )
        cond = Transaction.id.in_(linked)
        query = query.where(cond if reconciliation == "linked" else ~cond)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(Transaction.description_raw.ilike(like), Transaction.reference.ilike(like))
        )
    total = s.scalar(select(func.count()).select_from(query.subquery()))
    summary = _totals(s, query)
    col = SORTS.get(sort, Transaction.txn_date)
    query = query.order_by(col.asc() if order == "asc" else col.desc(), Transaction.id.desc())
    rows = s.scalars(query.limit(min(limit, 1000)).offset(offset)).unique().all()
    return {"total": total, "items": [ser.transaction(t) for t in rows], **summary}


def _totals(s: Session, query: Any) -> dict[str, Any]:
    """In/out sums of every row matching the filter (not just the page), per currency and
    per source statement, in each transaction's own currency so they can be checked
    against the statement."""
    sub = query.subquery()
    amt = sub.c.amount
    inflow = func.sum(case((amt > 0, amt), else_=0))
    outflow = func.sum(case((amt < 0, amt), else_=0))

    def fmt(v: Any) -> str:
        return str(Decimal(v or 0).quantize(Decimal("0.01")))

    by_ccy = s.execute(
        select(sub.c.currency, inflow, outflow, func.count()).group_by(sub.c.currency)
    ).all()
    by_doc = s.execute(
        select(
            sub.c.document_id,
            Document.original_filename,
            Document.statement_start,
            Document.statement_end,
            sub.c.currency,
            inflow,
            outflow,
            func.count(),
        )
        .outerjoin(Document, Document.id == sub.c.document_id)
        .group_by(sub.c.document_id, sub.c.currency)
        .order_by(Document.statement_end.desc(), sub.c.document_id.desc())
    ).all()
    return {
        "totals": [
            {
                "currency": c,
                "inflow": fmt(i),
                "outflow": fmt(o),
                "net": fmt((i or 0) + (o or 0)),
                "count": n,
            }
            for c, i, o, n in by_ccy
        ],
        "by_source": [
            {
                "document_id": d,
                "name": name or "Manual entries",
                "statement_start": st,
                "statement_end": en,
                "currency": c,
                "inflow": fmt(i),
                "outflow": fmt(o),
                "count": n,
            }
            for d, name, st, en, c, i, o, n in by_doc
        ],
    }


@router.get("/transactions/{txn_id}")
def get_transaction(txn_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    t = s.get(Transaction, txn_id)
    if t is None:
        raise not_found("transaction")
    out = ser.transaction(t)
    out["description_normalized"] = t.description_normalized
    out["source_ref"] = t.source_ref
    out["raw"] = t.raw
    out["classification_evidence"] = t.classification_evidence
    out["classification_config_version"] = t.classification_config_version
    out["document"] = (
        {
            "id": t.document.id,
            "filename": t.document.original_filename,
            "institution": t.document.institution.name if t.document.institution else None,
        }
        if t.document
        else None
    )
    links = s.scalars(
        select(ReconciliationLink).where(
            or_(
                ReconciliationLink.from_transaction_id == t.id,
                ReconciliationLink.to_transaction_id == t.id,
            )
        )
    ).all()
    out["links"] = []
    for lk in links:
        other_id = (
            lk.to_transaction_id if lk.from_transaction_id == t.id else lk.from_transaction_id
        )
        other = s.get(Transaction, other_id)
        out["links"].append(
            {**ser.link(lk), "counterpart": ser.transaction(other) if other else None}
        )
    history = s.scalars(
        select(ClassificationRecord)
        .where(ClassificationRecord.transaction_id == t.id)
        .order_by(ClassificationRecord.id)
    ).all()
    cats = {c.id: c.name for c in s.scalars(select(Category)).all()}
    execs = {
        e.id: e
        for e in s.scalars(
            select(AIExecution).where(
                AIExecution.id.in_([h.ai_execution_id for h in history if h.ai_execution_id])
            )
        ).all()
    }
    out["history"] = [
        {
            "at": h.created_at,
            "method": h.method,
            "category": cats.get(h.category_id),
            "confidence": h.confidence,
            "evidence": h.evidence,
            "config_version": h.config_version,
            "model": (execs[h.ai_execution_id].model if h.ai_execution_id in execs else None),
            "provider": (
                execs[h.ai_execution_id].provider_id if h.ai_execution_id in execs else None
            ),
        }
        for h in history
    ]
    out["overrides"] = [
        {
            "at": o.created_at,
            "field": o.field,
            "old": o.old_value,
            "new": o.new_value,
            "apply_to_similar": o.apply_to_similar,
        }
        for o in s.scalars(
            select(TransactionOverride)
            .where(TransactionOverride.transaction_id == t.id)
            .order_by(TransactionOverride.id)
        ).all()
    ]
    return out


class OverrideBody(BaseModel):
    field: str
    value: Any = None
    apply_to_similar: bool = False


@router.post("/transactions/{txn_id}/override")
def override(
    txn_id: int, body: OverrideBody, request: Request, s: Session = Depends(get_session)
) -> dict[str, Any]:
    t = s.get(Transaction, txn_id)
    if t is None:
        raise not_found("transaction")
    try:
        res = apply_override(s, t, body.field, body.value, apply_to_similar=body.apply_to_similar)
    except ValueError as e:
        raise bad_request(str(e)) from e
    if body.field in ("account", "direction"):
        enqueue(s, "reconcile", {}, dedupe_key="reconcile")
    notify_worker(request)
    return {"transaction": ser.transaction(t), **res}


@router.delete("/transactions/{txn_id}/override/{field}")
def unpin(txn_id: int, field: str, s: Session = Depends(get_session)) -> dict[str, Any]:
    """Release a pinned field back to automatic classification."""
    t = s.get(Transaction, txn_id)
    if t is None:
        raise not_found("transaction")
    t.pinned_fields = [p for p in (t.pinned_fields or []) if p != field]
    if field == "category":
        t.classification_method = None
        t.category_id = None
        s.flush()
        Classifier(s).classify([t])
    return ser.transaction(t)


class ManualTxn(BaseModel):
    account_id: int
    txn_date: date
    description: str
    amount: str  # signed: negative = outflow
    currency: str | None = None
    category_id: int | None = None
    owner_identity_id: int | None = None


@router.post("/transactions")
def create_manual(body: ManualTxn, request: Request, s: Session = Depends(get_session)):
    acct = s.get(Account, body.account_id)
    if acct is None:
        raise bad_request("unknown account")
    try:
        amount = Decimal(body.amount)
    except InvalidOperation as e:
        raise bad_request("invalid amount") from e
    if amount == 0:
        raise bad_request("amount cannot be zero")
    fp = hashlib.sha256(f"manual|{uuid.uuid4()}".encode()).hexdigest()
    t = Transaction(
        account_id=acct.id,
        txn_date=body.txn_date,
        description_raw=body.description,
        description_normalized=normalize_description(body.description),
        amount=amount,
        currency=(body.currency or acct.currency).upper(),
        direction="inflow" if amount > 0 else "outflow",
        entry_method="manual",
        fingerprint=fp,
        owner_identity_id=body.owner_identity_id,
    )
    t.account = acct
    apply_base_amount(s, t, base_currency(s))
    s.add(t)
    s.flush()
    if body.category_id:
        apply_override(s, t, "category", body.category_id)
    else:
        Classifier(s).classify([t])
    enqueue(s, "reconcile", {}, dedupe_key="reconcile")
    notify_worker(request)
    return ser.transaction(t)


@router.delete("/transactions/{txn_id}")
def delete_manual(txn_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    t = s.get(Transaction, txn_id)
    if t is None:
        raise not_found("transaction")
    if t.entry_method != "manual":
        raise bad_request("only manual entries can be deleted; delete the source document instead")
    s.delete(t)
    return {"ok": True}


# -- reconciliation ------------------------------------------------------------------------


@router.get("/reconciliation/links")
def list_links(
    kind: str | None = None,
    status: str | None = None,
    sort: str = "recent",  # recent|confidence (least certain first, for review)
    limit: int = 200,
    s: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    order = (
        (ReconciliationLink.confidence.asc(), ReconciliationLink.id.desc())
        if sort == "confidence"
        else (ReconciliationLink.id.desc(),)
    )
    q = select(ReconciliationLink).order_by(*order).limit(limit)
    if kind:
        q = q.where(ReconciliationLink.kind == kind)
    if status:
        q = q.where(ReconciliationLink.status == status)
    out = []
    for lk in s.scalars(q).all():
        a = s.get(Transaction, lk.from_transaction_id)
        b = s.get(Transaction, lk.to_transaction_id)
        out.append(
            {
                **ser.link(lk),
                "from": ser.transaction(a) if a else None,
                "to": ser.transaction(b) if b else None,
            }
        )
    return out


@router.get("/reconciliation/summary")
def links_summary(s: Session = Depends(get_session)) -> dict[str, Any]:
    """Link counts by status and kind; ``to_review`` drives the navigation badge."""
    rows = s.execute(
        select(ReconciliationLink.status, ReconciliationLink.kind, func.count()).group_by(
            ReconciliationLink.status, ReconciliationLink.kind
        )
    ).all()
    by_status: dict[str, dict[str, int]] = {}
    for status, kind, n in rows:
        by_status.setdefault(status, {})[kind] = n
    return {
        "to_review": sum(by_status.get("auto", {}).values()),
        "by_status": by_status,
    }


class LinkStatus(BaseModel):
    status: str
    note: str | None = None


@router.post("/reconciliation/links/{link_id}")
def update_link(link_id: int, body: LinkStatus, s: Session = Depends(get_session)):
    try:
        set_link_status(s, link_id, body.status, body.note)
    except ValueError as e:
        raise bad_request(str(e)) from e
    return {"ok": True}


class ManualLink(BaseModel):
    kind: str
    from_transaction_id: int
    to_transaction_id: int


@router.post("/reconciliation/links")
def create_link(body: ManualLink, s: Session = Depends(get_session)) -> dict[str, Any]:
    from ledger.reconciliation.engine import Reconciler

    a, b = s.get(Transaction, body.from_transaction_id), s.get(Transaction, body.to_transaction_id)
    if not a or not b:
        raise not_found("transaction")
    r = Reconciler(s, use_ai=False)
    lk = r._link(body.kind, a, b, 1.0, "user", {"source": "user"})  # noqa: SLF001
    lk.status = "confirmed"
    slug = {"internal_transfer": "internal-transfer", "card_settlement": "card-settlement"}.get(
        body.kind
    )
    if slug:
        for t in (a, b):
            r._set_category(t, slug, 1.0, {"link": body.kind, "source": "user"})  # noqa: SLF001
    if body.kind == "refund":
        r._set_category(b, "refund", 1.0, {"link": "refund", "source": "user"})  # noqa: SLF001
    if body.kind == "duplicate":
        b.duplicate_of_id = a.id
    return ser.link(lk)


@router.post("/reconciliation/run")
def run_reconciliation(request: Request, s: Session = Depends(get_session)) -> dict[str, Any]:
    job = enqueue(s, "reconcile", {}, dedupe_key="reconcile")
    notify_worker(request)
    return {"job_id": job.id}
