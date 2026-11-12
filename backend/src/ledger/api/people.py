"""Identities, institutions and accounts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ledger.api import serializers as ser
from ledger.api.deps import bad_request, get_session, not_found, notify_worker
from ledger.config import bump_version
from ledger.models import (
    ACCOUNT_TYPES,
    Account,
    AccountOwner,
    Identity,
    IdentityAlias,
    Institution,
    Transaction,
)
from ledger.propagation import after_identity_change
from ledger.text import last4, normalize_name

router = APIRouter(tags=["people & accounts"])


class IdentityBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = None
    kind: str = "individual"
    identifiers: list[str] = []
    aliases: list[str] = []


def _set_aliases(ident: Identity, aliases: list[str]) -> None:
    wanted = {normalize_name(a): a.strip() for a in aliases if a.strip()}
    for a in list(ident.aliases):
        if a.normalized not in wanted:
            ident.aliases.remove(a)
    have = {a.normalized for a in ident.aliases}
    for norm, raw in wanted.items():
        if norm not in have:
            ident.aliases.append(IdentityAlias(alias=raw, normalized=norm))


@router.get("/identities")
def list_identities(s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [ser.identity(i) for i in s.scalars(select(Identity).order_by(Identity.id)).all()]


@router.post("/identities")
def create_identity(body: IdentityBody, request: Request, s: Session = Depends(get_session)):
    if body.kind not in ("individual", "household"):
        raise bad_request("kind must be individual or household")
    ident = Identity(
        display_name=body.display_name.strip(),
        legal_name=body.legal_name,
        kind=body.kind,
        identifiers=body.identifiers,
    )
    _set_aliases(ident, body.aliases)
    s.add(ident)
    s.flush()
    after_identity_change(s, f"Identity '{ident.display_name}' added")
    notify_worker(request)
    return ser.identity(ident)


@router.put("/identities/{identity_id}")
def update_identity(
    identity_id: int, body: IdentityBody, request: Request, s: Session = Depends(get_session)
):
    ident = s.get(Identity, identity_id)
    if ident is None:
        raise not_found("identity")
    ident.display_name = body.display_name.strip()
    ident.legal_name = body.legal_name
    ident.kind = body.kind
    ident.identifiers = body.identifiers
    _set_aliases(ident, body.aliases)
    s.flush()
    after_identity_change(s, f"Identity '{ident.display_name}' updated")
    notify_worker(request)
    return ser.identity(ident)


@router.delete("/identities/{identity_id}")
def delete_identity(identity_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    ident = s.get(Identity, identity_id)
    if ident is None:
        raise not_found("identity")
    s.delete(ident)
    bump_version(s, "identities", "delete", "Identity removed")
    return {"ok": True}


# -- institutions --------------------------------------------------------------------------


class InstitutionBody(BaseModel):
    name: str
    aliases: list[str] = []
    country: str | None = None


@router.get("/institutions")
def list_institutions(s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [
        {"id": i.id, "name": i.name, "aliases": i.aliases or [], "country": i.country}
        for i in s.scalars(select(Institution).order_by(Institution.name)).all()
    ]


@router.post("/institutions")
def create_institution(body: InstitutionBody, s: Session = Depends(get_session)):
    if s.scalar(select(Institution).where(Institution.name == body.name)):
        raise bad_request("institution already exists")
    i = Institution(name=body.name, aliases=body.aliases, country=body.country)
    s.add(i)
    s.flush()
    bump_version(s, "accounts", "institution", f"Institution '{i.name}' added")
    return {"id": i.id, "name": i.name, "aliases": i.aliases, "country": i.country}


# -- accounts ------------------------------------------------------------------------------


class AccountBody(BaseModel):
    name: str
    account_type: str = "savings"
    institution_id: int | None = None
    masked_number: str | None = None
    currency: str
    aliases: list[str] = []
    owner_ids: list[int] = []
    active: bool = True


@router.get("/accounts")
def list_accounts(s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    counts = dict(
        s.execute(
            select(Transaction.account_id, func.count(Transaction.id))
            .where(Transaction.duplicate_of_id.is_(None))
            .group_by(Transaction.account_id)
        ).all()
    )
    latest = dict(
        s.execute(
            select(Transaction.account_id, func.max(Transaction.txn_date)).group_by(
                Transaction.account_id
            )
        ).all()
    )
    out = []
    for a in s.scalars(select(Account).order_by(Account.id)).all():
        d = ser.account(a)
        d["transaction_count"] = counts.get(a.id, 0)
        d["last_transaction"] = latest.get(a.id)
        bal = s.scalar(
            select(Transaction.balance_after)
            .where(
                Transaction.account_id == a.id,
                Transaction.balance_after.is_not(None),
                Transaction.duplicate_of_id.is_(None),
            )
            .order_by(Transaction.txn_date.desc(), Transaction.id.desc())
            .limit(1)
        )
        d["last_balance"] = ser.money(bal)
        out.append(d)
    return out


def _apply_account(a: Account, body: AccountBody) -> None:
    if body.account_type not in ACCOUNT_TYPES:
        raise bad_request(f"account_type must be one of {', '.join(ACCOUNT_TYPES)}")
    a.name = body.name
    a.account_type = body.account_type
    a.institution_id = body.institution_id
    # Only the last four digits are ever stored.
    a.masked_number = last4(body.masked_number) if body.masked_number else None
    a.currency = body.currency.upper()
    a.aliases = body.aliases
    a.active = body.active
    wanted = set(body.owner_ids)
    for o in list(a.owners):
        if o.identity_id not in wanted:
            a.owners.remove(o)
    have = {o.identity_id for o in a.owners}
    for iid in wanted:
        if iid in have:
            for o in a.owners:
                if o.identity_id == iid:
                    o.source, o.confidence = "user", 1.0
        else:
            a.owners.append(AccountOwner(identity_id=iid, source="user", confidence=1.0))


@router.post("/accounts")
def create_account(body: AccountBody, s: Session = Depends(get_session)):
    a = Account(name=body.name, currency=body.currency.upper(), auto_discovered=False)
    _apply_account(a, body)
    s.add(a)
    s.flush()
    bump_version(s, "accounts", "create", f"Account '{a.name}' added")
    return ser.account(a)


@router.put("/accounts/{account_id}")
def update_account(
    account_id: int, body: AccountBody, request: Request, s: Session = Depends(get_session)
):
    a = s.get(Account, account_id)
    if a is None:
        raise not_found("account")
    _apply_account(a, body)
    s.flush()
    bump_version(
        s, "accounts", "update", f"Account '{a.name}' updated", propagation="deterministic"
    )
    from ledger.jobs import enqueue

    # account types and ownership influence rules and reconciliation
    enqueue(s, "reclassify", {"all": True, "use_ai": False}, dedupe_key="reclassify:rules")
    enqueue(s, "reconcile", {}, dedupe_key="reconcile")
    notify_worker(request)
    return ser.account(a)


@router.post("/accounts/{source_id}/merge-into/{target_id}")
def merge_accounts(source_id: int, target_id: int, s: Session = Depends(get_session)):
    """Merge an auto-discovered duplicate account into another one."""
    from sqlalchemy import update

    from ledger.models import Document

    src, tgt = s.get(Account, source_id), s.get(Account, target_id)
    if not src or not tgt or src.id == tgt.id:
        raise bad_request("invalid accounts")
    n = s.execute(
        update(Transaction).where(Transaction.account_id == src.id).values(account_id=tgt.id)
    ).rowcount
    s.execute(update(Document).where(Document.account_id == src.id).values(account_id=tgt.id))
    s.delete(src)
    bump_version(s, "accounts", "merge", f"Account merged into '{tgt.name}'")
    return {"moved_transactions": n}
