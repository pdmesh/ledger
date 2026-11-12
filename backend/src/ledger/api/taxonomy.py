"""Taxonomy, merchants and classification rules."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ledger import propagation
from ledger.api import serializers as ser
from ledger.api.deps import bad_request, get_session, not_found, notify_worker
from ledger.classification.merchants import merge_merchants
from ledger.config import bump_version
from ledger.models import (
    ROLES,
    Category,
    ClassificationRule,
    Merchant,
    MerchantAlias,
    Transaction,
)
from ledger.text import normalize_description, slugify

router = APIRouter(tags=["taxonomy"])


# -- categories ----------------------------------------------------------------------------


@router.get("/categories")
def list_categories(
    include_inactive: bool = False, s: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    counts = dict(
        s.execute(
            select(Transaction.category_id, func.count(Transaction.id))
            .where(Transaction.duplicate_of_id.is_(None))
            .group_by(Transaction.category_id)
        ).all()
    )
    q = select(Category).order_by(Category.role, Category.sort_order, Category.name)
    if not include_inactive:
        q = q.where(Category.active.is_(True))
    out = []
    for c in s.scalars(q).all():
        d = ser.category(c)
        d["transaction_count"] = counts.get(c.id, 0)
        out.append(d)
    return out


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None
    description: str = ""
    role: str | None = None
    slug: str | None = None


@router.post("/categories")
def create_category(body: CategoryCreate, request: Request, s: Session = Depends(get_session)):
    if body.parent_id is None and body.role not in ROLES:
        raise bad_request(f"role must be one of {', '.join(ROLES)}")
    slug = body.slug or slugify(body.name)
    base, i = slug, 2
    while s.scalar(select(Category.id).where(Category.slug == slug)):
        slug, i = f"{base}-{i}", i + 1
    try:
        c = propagation.create_category(
            s,
            name=body.name,
            slug=slug,
            parent_id=body.parent_id,
            description=body.description,
            role=body.role,
        )
    except ValueError as e:
        raise bad_request(str(e)) from e
    notify_worker(request)
    return ser.category(c)


class CategoryPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: int | None = None
    active: bool | None = None


@router.patch("/categories/{category_id}")
def patch_category(
    category_id: int, body: CategoryPatch, request: Request, s: Session = Depends(get_session)
):
    c = s.get(Category, category_id)
    if c is None:
        raise not_found("category")
    changes = body.model_dump(exclude_unset=True)
    try:
        mode = propagation.update_category(s, c, changes)
    except ValueError as e:
        raise bad_request(str(e)) from e
    notify_worker(request)
    return {"category": ser.category(c), "propagation": mode}


@router.post("/categories/{source_id}/merge-into/{target_id}")
def merge_category(source_id: int, target_id: int, s: Session = Depends(get_session)):
    src, tgt = s.get(Category, source_id), s.get(Category, target_id)
    if src is None or tgt is None:
        raise not_found("category")
    try:
        n = propagation.merge_categories(s, src, tgt)
    except ValueError as e:
        raise bad_request(str(e)) from e
    return {"moved_transactions": n}


# -- merchants -----------------------------------------------------------------------------


@router.get("/merchants")
def list_merchants(
    q: str | None = None, limit: int = 200, offset: int = 0, s: Session = Depends(get_session)
) -> dict[str, Any]:
    counts = (
        select(Transaction.merchant_id, func.count(Transaction.id).label("n"))
        .where(Transaction.duplicate_of_id.is_(None))
        .group_by(Transaction.merchant_id)
        .subquery()
    )
    query = select(Merchant, func.coalesce(counts.c.n, 0)).outerjoin(
        counts, counts.c.merchant_id == Merchant.id
    )
    if q:
        query = query.where(Merchant.canonical_name.ilike(f"%{q}%"))
    total = s.scalar(select(func.count()).select_from(query.subquery()))
    rows = s.execute(
        query.order_by(func.coalesce(counts.c.n, 0).desc(), Merchant.canonical_name)
        .limit(limit)
        .offset(offset)
    ).all()
    return {"total": total, "items": [ser.merchant(m, n) for m, n in rows]}


class MerchantPatch(BaseModel):
    canonical_name: str | None = None
    description: str | None = None
    default_category_id: int | None = None


@router.patch("/merchants/{merchant_id}")
def patch_merchant(
    merchant_id: int, body: MerchantPatch, request: Request, s: Session = Depends(get_session)
):
    m = s.get(Merchant, merchant_id)
    if m is None:
        raise not_found("merchant")
    changes = body.model_dump(exclude_unset=True)
    propagated = 0
    if "canonical_name" in changes and changes["canonical_name"]:
        m.canonical_name = changes["canonical_name"].strip()
        m.source = "user"
    if "description" in changes:
        m.description = changes["description"] or ""
    if "default_category_id" in changes:
        propagated = propagation.set_merchant_mapping(s, m, changes["default_category_id"])
    else:
        bump_version(s, "merchants", "update", f"Merchant '{m.canonical_name}' updated")
    notify_worker(request)
    return {"merchant": ser.merchant(m), "reclassified": propagated}


class AliasBody(BaseModel):
    pattern: str
    match_type: str = "contains"


@router.post("/merchants/{merchant_id}/aliases")
def add_alias(
    merchant_id: int, body: AliasBody, request: Request, s: Session = Depends(get_session)
):
    m = s.get(Merchant, merchant_id)
    if m is None:
        raise not_found("merchant")
    if body.match_type not in ("key", "contains", "regex"):
        raise bad_request("match_type must be key, contains or regex")
    pattern = body.pattern if body.match_type == "regex" else normalize_description(body.pattern)
    existing = s.scalar(
        select(MerchantAlias).where(
            MerchantAlias.pattern == pattern, MerchantAlias.match_type == body.match_type
        )
    )
    if existing:
        existing.merchant_id, existing.source = m.id, "user"
    else:
        s.add(
            MerchantAlias(
                merchant_id=m.id, pattern=pattern, match_type=body.match_type, source="user"
            )
        )
    s.flush()
    propagation.after_alias_change(s, m)
    notify_worker(request)
    return ser.merchant(m)


@router.delete("/merchants/{merchant_id}/aliases/{alias_id}")
def delete_alias(merchant_id: int, alias_id: int, s: Session = Depends(get_session)):
    a = s.get(MerchantAlias, alias_id)
    if a is None or a.merchant_id != merchant_id:
        raise not_found("alias")
    s.delete(a)
    bump_version(s, "merchants", "alias", "Merchant alias removed")
    return {"ok": True}


@router.post("/merchants/{source_id}/merge-into/{target_id}")
def merge_merchant(
    source_id: int, target_id: int, request: Request, s: Session = Depends(get_session)
):
    try:
        n = merge_merchants(s, source_id, target_id)
    except ValueError as e:
        raise bad_request(str(e)) from e
    tgt = s.get(Merchant, target_id)
    tgt.source = "user" if tgt.source == "auto" else tgt.source
    bump_version(
        s,
        "merchants",
        "merge",
        f"Merchants merged into '{tgt.canonical_name}'",
        propagation="deterministic",
    )
    propagation.reclassify(s, {"merchant_ids": [target_id]}, use_ai=False)
    notify_worker(request)
    return {"moved_transactions": n}


# -- rules ---------------------------------------------------------------------------------


class RuleBody(BaseModel):
    name: str
    priority: int = 50
    conditions: dict[str, Any]
    actions: dict[str, Any]
    active: bool = True
    confidence: float = 0.95


def _validate_rule(s: Session, body: RuleBody) -> None:
    slug = body.actions.get("category")
    if slug and not s.scalar(select(Category.id).where(Category.slug == slug)):
        raise bad_request(f"unknown category '{slug}'")
    if not any(
        body.conditions.get(k)
        for k in ("description_contains", "description_regex", "account_ids", "merchant_ids")
    ):
        raise bad_request("a rule needs a description, account or merchant condition")


@router.get("/rules")
def list_rules(s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rules = s.scalars(select(ClassificationRule)).all()
    rules = sorted(rules, key=lambda r: (r.source == "system", r.priority, r.id))
    return [ser.rule(r) for r in rules]


@router.post("/rules")
def create_rule(body: RuleBody, request: Request, s: Session = Depends(get_session)):
    _validate_rule(s, body)
    r = ClassificationRule(**body.model_dump(), source="user")
    s.add(r)
    s.flush()
    propagation.after_rule_change(s, r)
    notify_worker(request)
    return ser.rule(r)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleBody, request: Request, s: Session = Depends(get_session)):
    r = s.get(ClassificationRule, rule_id)
    if r is None:
        raise not_found("rule")
    _validate_rule(s, body)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    s.flush()
    propagation.after_rule_change(s, r)
    notify_worker(request)
    return ser.rule(r)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, request: Request, s: Session = Depends(get_session)):
    r = s.get(ClassificationRule, rule_id)
    if r is None:
        raise not_found("rule")
    r.active = False if r.source == "system" else r.active
    if r.source != "system":
        s.delete(r)
    s.flush()
    propagation.after_rule_change(s, r)
    notify_worker(request)
    return {"ok": True}
