"""Deterministic analytics over the ledger.

All figures are in the base currency (``base_amount``), exclude detected duplicates, and
derive meaning from category *roles*:

* income       -- inflows with role ``income``
* consumption  -- net outflows with role ``expense`` minus refunds (role ``adjustment``)
* investment   -- outflows/inflows with role ``investment``
* transfers    -- role ``transfer`` (internal transfers, card settlements, cash moves);
                  excluded from income/consumption so nothing is counted twice.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Integer, Select, String, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from ledger.models import Account, AccountOwner, Category, Identity, Merchant, Transaction

ZERO = Decimal(0)


@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    identity_id: int | None = None  # individual view (own + joint accounts, or attributed)
    scope: str = "household"  # household|individual|joint
    account_ids: list[int] = field(default_factory=list)
    institution_ids: list[int] = field(default_factory=list)
    currency: str | None = None
    include_duplicates: bool = False


def _joint_account_ids(session: Session) -> Select[Any]:
    return (
        select(AccountOwner.account_id)
        .group_by(AccountOwner.account_id)
        .having(func.count(AccountOwner.identity_id) > 1)
    )


def apply_filters(q: Select[Any], f: Filters, session: Session) -> Select[Any]:
    if not f.include_duplicates:
        q = q.where(Transaction.duplicate_of_id.is_(None))
    if f.date_from:
        q = q.where(Transaction.txn_date >= f.date_from)
    if f.date_to:
        q = q.where(Transaction.txn_date <= f.date_to)
    if f.account_ids:
        q = q.where(Transaction.account_id.in_(f.account_ids))
    if f.institution_ids:
        q = q.where(
            Transaction.account_id.in_(
                select(Account.id).where(Account.institution_id.in_(f.institution_ids))
            )
        )
    if f.currency:
        q = q.where(Transaction.currency == f.currency)
    if f.scope == "joint":
        q = q.where(Transaction.account_id.in_(_joint_account_ids(session)))
    if f.identity_id is not None and f.scope in ("individual", "household"):
        owned = select(AccountOwner.account_id).where(AccountOwner.identity_id == f.identity_id)
        q = q.where(
            or_(
                Transaction.owner_identity_id == f.identity_id,
                and_(Transaction.owner_identity_id.is_(None), Transaction.account_id.in_(owned)),
            )
        )
    return q


def _role_expr() -> Any:
    # Uncategorized rows fall back to a role by direction
    return func.coalesce(
        Category.role,
        case((Transaction.amount < 0, "expense"), else_="income"),
    )


def _dec(v: Any) -> Decimal:
    return Decimal(v) if v is not None else ZERO


def summarize_roles(rows: list[tuple[str, Decimal, Decimal]]) -> dict[str, Decimal]:
    """rows: (role, sum_inflow, sum_outflow[negative]) -> metric dict."""
    by = {r: (_dec(i), _dec(o)) for r, i, o in rows}

    def g(role: str, idx: int) -> Decimal:
        return by.get(role, (ZERO, ZERO))[idx]

    total_in = sum((v[0] for v in by.values()), ZERO)
    total_out = -sum((v[1] for v in by.values()), ZERO)
    consumption = -(g("expense", 0) + g("expense", 1) + g("adjustment", 0) + g("adjustment", 1))
    income = g("income", 0) + g("income", 1)
    inv_out = -g("investment", 1)
    inv_in = g("investment", 0)
    transfers = -g("transfer", 1)
    external_in = total_in - g("transfer", 0)
    external_out = total_out + g("transfer", 1)
    return {
        "total_inflows": total_in,
        "total_outflows": total_out,
        "external_inflows": external_in,
        "external_outflows": external_out,
        "net_cash_flow": external_in - external_out,
        "income": income,
        "consumption": consumption,
        "refunds": g("adjustment", 0),
        "investment_outflows": inv_out,
        "investment_inflows": inv_in,
        "net_invested": inv_out - inv_in,
        "transfers": transfers,
        "savings_rate": (
            ((income - consumption) / income).quantize(Decimal("0.0001")) if income else None
        ),
    }


def overview(session: Session, f: Filters) -> dict[str, Any]:
    amt = Transaction.base_amount
    role = _role_expr().label("role")
    q = (
        select(
            role,
            func.sum(case((amt > 0, amt), else_=0)),
            func.sum(case((amt < 0, amt), else_=0)),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
    )
    q = apply_filters(q, f, session).group_by(role)
    metrics = summarize_roles([(r, _dec(i), _dec(o)) for r, i, o in session.execute(q).all()])

    cnt_q = apply_filters(
        select(
            func.count(Transaction.id),
            func.sum(case((Transaction.base_amount.is_(None), 1), else_=0)),
            func.sum(case((Transaction.classification_confidence < 0.5, 1), else_=0)),
            func.min(Transaction.txn_date),
            func.max(Transaction.txn_date),
        ).select_from(Transaction),
        f,
        session,
    )
    count, unconverted, low_conf, dmin, dmax = session.execute(cnt_q).one()
    return {
        "metrics": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in metrics.items()},
        "transaction_count": count or 0,
        "unconverted_count": unconverted or 0,
        "low_confidence_count": low_conf or 0,
        "date_range": [dmin, dmax],
        "series": timeseries(session, f, "month"),
    }


def _period_expr(granularity: str) -> Any:
    d = Transaction.txn_date
    if granularity == "year":
        return func.strftime("%Y", d)
    if granularity == "quarter":
        quarter = (cast(func.strftime("%m", d), Integer) + 2) / 3
        return func.strftime("%Y", d).op("||")(literal("-Q")).op("||")(cast(quarter, String))
    if granularity == "day":
        return func.strftime("%Y-%m-%d", d)
    return func.strftime("%Y-%m", d)


def timeseries(session: Session, f: Filters, granularity: str = "month") -> list[dict[str, Any]]:
    amt = Transaction.base_amount
    period = _period_expr(granularity).label("period")
    role = _role_expr().label("role")
    q = (
        select(
            period,
            role,
            func.sum(case((amt > 0, amt), else_=0)),
            func.sum(case((amt < 0, amt), else_=0)),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
    )
    q = apply_filters(q, f, session).group_by(period, role).order_by(period)
    grouped: dict[str, list[tuple[str, Decimal, Decimal]]] = defaultdict(list)
    for p, r, i, o in session.execute(q).all():
        grouped[str(p)].append((r, _dec(i), _dec(o)))
    out = []
    for p in sorted(grouped):
        m = summarize_roles(grouped[p])
        out.append(
            {"period": p, **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in m.items()}}
        )
    return out


def by_category(
    session: Session, f: Filters, role: str | None = None, granularity: str | None = None
) -> list[dict[str, Any]]:
    amt = Transaction.base_amount
    cols: list[Any] = [Transaction.category_id, func.sum(amt), func.count(Transaction.id)]
    if granularity:
        cols.insert(0, _period_expr(granularity).label("period"))
    q = (
        select(*cols)
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
    )
    if role:
        q = q.where(_role_expr() == role)
    q = apply_filters(q, f, session)
    q = q.group_by(*([cols[0]] if granularity else []), Transaction.category_id)
    cats = {c.id: c for c in session.scalars(select(Category)).all()}
    out = []
    for row in session.execute(q).all():
        if granularity:
            period, cid, total, n = row
        else:
            period, (cid, total, n) = None, row
        c = cats.get(cid)
        parent = cats.get(c.parent_id) if c and c.parent_id else None
        item = {
            "category_id": cid,
            "slug": c.slug if c else None,
            "name": c.name if c else "Uncategorized",
            "parent": parent.name if parent and parent.parent_id else None,
            "role": c.role if c else None,
            "total": str(_dec(total)),
            "count": n,
        }
        if period:
            item["period"] = period
        out.append(item)
    out.sort(key=lambda x: abs(Decimal(x["total"])), reverse=True)
    return out


def by_merchant(
    session: Session, f: Filters, limit: int = 25, role: str | None = "expense"
) -> list[dict[str, Any]]:
    amt = Transaction.base_amount
    q = (
        select(
            Merchant.id,
            Merchant.canonical_name,
            func.sum(amt),
            func.count(Transaction.id),
            func.max(case((Transaction.is_recurring.is_(True), 1), else_=0)),
            func.min(Transaction.txn_date),
            func.max(Transaction.txn_date),
        )
        .select_from(Transaction)
        .join(Merchant, Merchant.id == Transaction.merchant_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
    )
    if role:
        q = q.where(_role_expr() == role)
    q = apply_filters(q, f, session).group_by(Merchant.id, Merchant.canonical_name)
    q = q.order_by(func.sum(amt)).limit(limit)
    return [
        {
            "merchant_id": mid,
            "name": name,
            "total": str(_dec(total)),
            "count": n,
            "recurring": bool(rec),
            "first": first,
            "last": last,
        }
        for mid, name, total, n, rec, first, last in session.execute(q).all()
    ]


def household(session: Session, f: Filters) -> list[dict[str, Any]]:
    out = []
    for ident in session.scalars(select(Identity)).all():
        fi = Filters(**{**f.__dict__, "identity_id": ident.id, "scope": "individual"})
        ov = overview(session, fi)
        out.append(
            {
                "identity_id": ident.id,
                "name": ident.display_name,
                "metrics": ov["metrics"],
                "transaction_count": ov["transaction_count"],
            }
        )
    fj = Filters(**{**f.__dict__, "identity_id": None, "scope": "joint"})
    ov = overview(session, fj)
    out.append(
        {
            "identity_id": None,
            "name": "Joint accounts",
            "metrics": ov["metrics"],
            "transaction_count": ov["transaction_count"],
        }
    )
    return out


def facts_for_query(session: Session, f: Filters) -> dict[str, Any]:
    """Compact pre-computed facts for natural-language questions (no raw rows)."""
    return {
        "filters": {k: str(v) for k, v in f.__dict__.items() if v},
        "overview": overview(session, f)["metrics"],
        "monthly": timeseries(session, f, "month")[-24:],
        "categories": by_category(session, f)[:40],
        "top_merchants": by_merchant(session, f, limit=25),
    }
