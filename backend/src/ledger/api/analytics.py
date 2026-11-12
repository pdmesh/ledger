from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ledger.analytics import service as an
from ledger.api.deps import bad_request, get_session
from ledger.intelligence.router import NoProviderAvailable
from ledger.intelligence.tasks import answer_query

router = APIRouter(prefix="/analytics", tags=["analytics"])


def filters(
    date_from: date | None = None,
    date_to: date | None = None,
    identity_id: int | None = None,
    scope: str = "household",
    account_id: list[int] = Query(default=[]),
    institution_id: list[int] = Query(default=[]),
    currency: str | None = None,
) -> an.Filters:
    if scope not in ("household", "individual", "joint"):
        raise bad_request("scope must be household, individual or joint")
    return an.Filters(date_from, date_to, identity_id, scope, account_id, institution_id, currency)


@router.get("/overview")
def overview(f: an.Filters = Depends(filters), s: Session = Depends(get_session)) -> dict:
    return an.overview(s, f)


@router.get("/timeseries")
def timeseries(
    granularity: str = "month", f: an.Filters = Depends(filters), s: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    if granularity not in ("day", "month", "quarter", "year"):
        raise bad_request("invalid granularity")
    return an.timeseries(s, f, granularity)


@router.get("/categories")
def categories(
    role: str | None = None,
    granularity: str | None = None,
    f: an.Filters = Depends(filters),
    s: Session = Depends(get_session),
):
    return an.by_category(s, f, role, granularity)


@router.get("/merchants")
def merchants(
    limit: int = 25,
    role: str | None = "expense",
    f: an.Filters = Depends(filters),
    s: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return an.by_merchant(s, f, limit, role or None)


@router.get("/household")
def household(f: an.Filters = Depends(filters), s: Session = Depends(get_session)):
    return an.household(s, f)


class QueryBody(BaseModel):
    question: str


@router.post("/ask")
def ask(body: QueryBody, f: an.Filters = Depends(filters), s: Session = Depends(get_session)):
    """Natural-language question answered from pre-computed aggregates (not raw rows)."""
    facts = an.facts_for_query(s, f)
    try:
        return answer_query(s, body.question, facts)
    except NoProviderAvailable as e:
        raise bad_request(
            "No intelligence provider is routed for 'query'. Configure one in Settings."
        ) from e
