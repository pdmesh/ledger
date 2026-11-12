"""Base-currency conversion using user-maintained historical rates.

Original amounts are always preserved; ``base_amount`` is derived and can be recomputed
whenever rates change. Rates are looked up for the transaction date or the closest
earlier date within ``max_staleness_days``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger.config import get_setting
from ledger.models import FxRate, Transaction


def base_currency(session: Session) -> str | None:
    return get_setting(session, "general").get("base_currency")


def lookup_rate(
    session: Session, on: date, from_ccy: str, to_ccy: str, max_staleness_days: int = 10
) -> Decimal | None:
    if from_ccy == to_ccy:
        return Decimal(1)
    for a, b, invert in ((from_ccy, to_ccy, False), (to_ccy, from_ccy, True)):
        r = session.scalar(
            select(FxRate)
            .where(
                FxRate.from_currency == a,
                FxRate.to_currency == b,
                FxRate.rate_date <= on,
                FxRate.rate_date >= on - timedelta(days=max_staleness_days),
            )
            .order_by(FxRate.rate_date.desc())
            .limit(1)
        )
        if r and r.rate:
            return (Decimal(1) / r.rate) if invert else r.rate
    return None


def apply_base_amount(session: Session, txn: Transaction, base: str | None) -> None:
    if not base:
        txn.base_amount, txn.fx_rate = txn.amount, None
        return
    if txn.currency == base:
        txn.base_amount, txn.fx_rate = txn.amount, None
        return
    rate = lookup_rate(session, txn.txn_date, txn.currency, base)
    if rate is None:
        txn.base_amount, txn.fx_rate = None, None
    else:
        txn.fx_rate = rate
        txn.base_amount = (Decimal(txn.amount) * rate).quantize(Decimal("0.0001"))


def recompute_all(session: Session) -> int:
    base = base_currency(session)
    n = 0
    for t in session.scalars(select(Transaction)).all():
        apply_base_amount(session, t, base)
        n += 1
    session.flush()
    return n
