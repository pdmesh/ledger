"""Configuration change propagation.

Every configuration edit is persisted and versioned, then classified as:

* ``none``          -- display-only (e.g. category rename): nothing to recompute.
* ``deterministic`` -- recompute with rules/mappings only (merge, move, mapping, rule, alias).
* ``ai``            -- meaning changed (category description/new category): affected rows
                       are re-run through the full chain, including models, asynchronously.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ledger.classification.engine import Classifier
from ledger.config import bump_version
from ledger.identity import resolve_account_owners
from ledger.jobs import enqueue
from ledger.models import (
    Account,
    Category,
    ClassificationRule,
    Document,
    Merchant,
    Transaction,
    TransactionOverride,
)

USER_FIELDS = {"category", "merchant", "account", "owner", "direction", "duplicate"}


# -- taxonomy ----------------------------------------------------------------------------


def _subtree(session: Session, root: Category) -> list[Category]:
    out, frontier = [root], [root.id]
    while frontier:
        kids = session.scalars(select(Category).where(Category.parent_id.in_(frontier))).all()
        out.extend(kids)
        frontier = [k.id for k in kids]
    return out


def create_category(
    session: Session,
    *,
    name: str,
    slug: str,
    parent_id: int | None,
    description: str = "",
    role: str | None = None,
) -> Category:
    parent = session.get(Category, parent_id) if parent_id else None
    if parent is None and role is None:
        raise ValueError("a root category needs a role")
    cat = Category(
        slug=slug,
        name=name,
        description=description,
        parent_id=parent_id,
        role=parent.role if parent else role,
    )
    session.add(cat)
    session.flush()
    bump_version(
        session,
        "taxonomy",
        "create",
        f"Category '{name}' added",
        detail={"category_id": cat.id},
        propagation="ai",
    )
    # a new category may better describe rows that are currently uncategorized/fallback
    enqueue(
        session,
        "reclassify",
        {"methods": ["fallback"], "use_ai": True},
        dedupe_key="reclassify:fallback",
    )
    return cat


def update_category(session: Session, cat: Category, changes: dict[str, Any]) -> str:
    propagation = "none"
    summary = []
    if "name" in changes and changes["name"] != cat.name:
        summary.append(f"renamed '{cat.name}' -> '{changes['name']}'")
        cat.name = changes["name"]
    if "description" in changes and changes["description"] != cat.description:
        cat.description = changes["description"]
        cat.semantic_version += 1
        propagation = "ai"
        summary.append(f"description of '{cat.name}' changed")
    if "parent_id" in changes and changes["parent_id"] != cat.parent_id:
        new_parent = session.get(Category, changes["parent_id"]) if changes["parent_id"] else None
        if cat.parent_id is None:
            raise ValueError("root categories cannot be moved")
        if new_parent is None:
            raise ValueError("a category must keep a parent")
        if new_parent.id in {c.id for c in _subtree(session, cat)}:
            raise ValueError("cannot move a category under itself")
        cat.parent_id = new_parent.id
        if new_parent.role != cat.role:
            for c in _subtree(session, cat):
                c.role = new_parent.role
            cat.semantic_version += 1
        propagation = "deterministic" if propagation == "none" else propagation
        summary.append(f"'{cat.name}' moved under '{new_parent.name}'")
    if "active" in changes and changes["active"] != cat.active:
        if cat.is_system and not changes["active"]:
            raise ValueError("system categories cannot be disabled")
        for c in _subtree(session, cat):
            c.active = bool(changes["active"])
        propagation = "ai"
        summary.append(f"'{cat.name}' {'enabled' if changes['active'] else 'disabled'}")
    session.flush()
    if summary:
        bump_version(
            session,
            "taxonomy",
            "update",
            "; ".join(summary),
            detail={"category_id": cat.id, **changes},
            propagation=propagation,
        )
    if propagation == "ai":
        ids = [c.id for c in _subtree(session, cat)]
        enqueue(
            session,
            "reclassify",
            {"category_ids": ids, "methods": ["llm", "fallback", "history"], "use_ai": True},
            dedupe_key=f"reclassify:cat:{cat.id}",
        )
    return propagation


def merge_categories(session: Session, source: Category, target: Category) -> int:
    if source.id == target.id:
        raise ValueError("cannot merge a category into itself")
    if source.parent_id is None:
        raise ValueError("root categories cannot be merged")
    n = (
        session.execute(
            update(Transaction)
            .where(Transaction.category_id == source.id)
            .values(category_id=target.id)
        ).rowcount
        or 0
    )
    session.execute(
        update(Merchant)
        .where(Merchant.default_category_id == source.id)
        .values(default_category_id=target.id)
    )
    session.execute(
        update(Category).where(Category.parent_id == source.id).values(parent_id=target.id)
    )
    for rule in session.scalars(select(ClassificationRule)).all():
        if (rule.actions or {}).get("category") == source.slug:
            rule.actions = {**rule.actions, "category": target.slug}
    source.active = False
    source.merged_into_id = target.id
    session.flush()
    bump_version(
        session,
        "taxonomy",
        "merge",
        f"'{source.name}' merged into '{target.name}'",
        detail={"source": source.id, "target": target.id, "transactions": n},
        propagation="deterministic",
    )
    return n


# -- merchants & rules -------------------------------------------------------------------


def set_merchant_mapping(session: Session, merchant: Merchant, category_id: int | None) -> int:
    merchant.default_category_id = category_id
    merchant.source = "user"
    session.flush()
    bump_version(
        session,
        "merchants",
        "mapping",
        f"Merchant '{merchant.canonical_name}' mapped",
        detail={"merchant_id": merchant.id, "category_id": category_id},
        propagation="deterministic",
    )
    return reclassify(session, {"merchant_ids": [merchant.id]}, use_ai=False)


def after_alias_change(session: Session, merchant: Merchant) -> None:
    bump_version(
        session,
        "merchants",
        "alias",
        f"Alias added to '{merchant.canonical_name}'",
        detail={"merchant_id": merchant.id},
        propagation="deterministic",
    )
    enqueue(session, "remap_merchants", {}, dedupe_key="remap_merchants")


def after_rule_change(session: Session, rule: ClassificationRule) -> None:
    bump_version(
        session,
        "rules",
        "update",
        f"Rule '{rule.name}' saved",
        detail={"rule_id": rule.id},
        propagation="deterministic",
    )
    enqueue(session, "reclassify", {"all": True, "use_ai": False}, dedupe_key="reclassify:rules")


def after_identity_change(session: Session, summary: str) -> None:
    bump_version(session, "identities", "update", summary, propagation="deterministic")
    enqueue(session, "resolve_owners", {}, dedupe_key="resolve_owners")


# -- reprocessing primitives (used by jobs) ----------------------------------------------


def reclassify(
    session: Session, flt: dict[str, Any], *, use_ai: bool = False, provider_factory: Any = None
) -> int:
    q = select(Transaction).where(Transaction.duplicate_of_id.is_(None))
    if flt.get("category_ids"):
        q = q.where(Transaction.category_id.in_(flt["category_ids"]))
    if flt.get("merchant_ids"):
        q = q.where(Transaction.merchant_id.in_(flt["merchant_ids"]))
    if flt.get("transaction_ids"):
        q = q.where(Transaction.id.in_(flt["transaction_ids"]))
    if flt.get("methods"):
        conds = [Transaction.classification_method.in_(flt["methods"])]
        if "fallback" in flt["methods"]:
            conds.append(Transaction.category_id.is_(None))
        q = q.where(or_(*conds))
    txns = [t for t in session.scalars(q).all() if "category" not in (t.pinned_fields or [])]
    if not txns:
        return 0
    clf = Classifier(session, use_ai=use_ai, provider_factory=provider_factory)
    clf.classify(txns, force=True, deterministic_only=not use_ai)
    return len(txns)


def remap_merchants(session: Session) -> int:
    from ledger.classification.merchants import MerchantResolver

    resolver = MerchantResolver(session)
    changed = []
    for t in session.scalars(select(Transaction)).all():
        if "merchant" in (t.pinned_fields or []):
            continue
        m, method = resolver.resolve(t.description_raw, create=False)
        if m and method == "alias" and m.id != t.merchant_id:
            t.merchant_id = m.id
            changed.append(t)
    session.flush()
    if changed:
        Classifier(session, use_ai=False).classify(changed, force=True, deterministic_only=True)
    return len(changed)


def resolve_all_owners(session: Session) -> int:
    n = 0
    for doc in session.scalars(select(Document).where(Document.account_id.is_not(None))).all():
        acct = session.get(Account, doc.account_id)
        if acct is None:
            continue
        ident = doc.identification or {}
        found = resolve_account_owners(
            session, acct, ident.get("holder_text"), ident.get("header_excerpt")
        )
        n += len(found)
    return n


# -- user corrections --------------------------------------------------------------------


def apply_override(
    session: Session, txn: Transaction, field: str, value: Any, *, apply_to_similar: bool = False
) -> dict[str, Any]:
    """Record a user correction, pin the field and optionally learn from it."""
    if field not in USER_FIELDS:
        raise ValueError(f"unsupported field {field}")
    result: dict[str, Any] = {"learned": None, "propagated": 0}
    if field == "category":
        cat = session.get(Category, value)
        if cat is None or not cat.active:
            raise ValueError("unknown category")
        old = txn.category_id
        txn.category_id = cat.id
        txn.classification_method = "user"
        txn.classification_confidence = 1.0
        txn.classification_evidence = {"source": "user override"}
    elif field == "merchant":
        if value is not None and session.get(Merchant, value) is None:
            raise ValueError("unknown merchant")
        old, txn.merchant_id = txn.merchant_id, value
    elif field == "account":
        if session.get(Account, value) is None:
            raise ValueError("unknown account")
        old, txn.account_id = txn.account_id, value
    elif field == "owner":
        old, txn.owner_identity_id = txn.owner_identity_id, value
    elif field == "direction":
        if value not in ("inflow", "outflow"):
            raise ValueError("direction must be inflow or outflow")
        old = txn.direction
        if value != txn.direction:
            txn.direction = value
            txn.amount = -txn.amount
            if txn.base_amount is not None:
                txn.base_amount = -txn.base_amount
    elif field == "duplicate":
        old, txn.duplicate_of_id = txn.duplicate_of_id, value
    pinned = set(txn.pinned_fields or [])
    pinned.add(field)
    txn.pinned_fields = sorted(pinned)
    session.add(
        TransactionOverride(
            transaction_id=txn.id,
            field=field,
            old_value=old,
            new_value=value,
            apply_to_similar=apply_to_similar,
        )
    )
    session.flush()

    if apply_to_similar and field == "category" and txn.merchant_id:
        merchant = session.get(Merchant, txn.merchant_id)
        if merchant is not None:
            result["learned"] = {"merchant_id": merchant.id, "category_id": value}
            result["propagated"] = set_merchant_mapping(session, merchant, value)
    return result
