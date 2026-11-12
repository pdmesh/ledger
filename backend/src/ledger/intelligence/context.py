"""Financial Context Package: per-task context generated from the current configuration.

The model is never expected to remember anything between calls; every prompt is built
from the database at the current configuration version.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger.config import current_version, get_setting
from ledger.models import (
    Account,
    Category,
    ClassificationRule,
    Identity,
    Merchant,
    Transaction,
    TransactionOverride,
)


@dataclass
class ContextPackage:
    config_version: int
    taxonomy: list[dict[str, Any]]
    accounts: list[dict[str, Any]]
    identities: list[dict[str, Any]]
    merchants: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    locale: dict[str, Any] = field(default_factory=dict)

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "locale": self.locale,
            "taxonomy": self.taxonomy,
            "accounts": self.accounts,
            "household": self.identities,
            "known_merchants": self.merchants,
            "user_rules": self.rules,
            "user_corrected_examples": self.examples,
        }


def taxonomy_for_prompt(session: Session) -> list[dict[str, Any]]:
    cats = session.scalars(select(Category).where(Category.active.is_(True))).all()
    by_id = {c.id: c for c in cats}
    out = []
    for c in sorted(cats, key=lambda c: (c.role, c.parent_id or 0, c.sort_order)):
        if c.parent_id is None:
            continue  # roles/roots are implied by "role"
        parent = by_id.get(c.parent_id)
        out.append(
            {
                "slug": c.slug,
                "name": c.name,
                "role": c.role,
                "parent": parent.slug if parent and parent.parent_id else None,
                "description": c.description,
            }
        )
    return out


def build_context(
    session: Session,
    *,
    for_cloud: bool,
    merchant_ids: Iterable[int] = (),
    merchant_keys: Iterable[str] = (),
    max_examples: int = 30,
) -> ContextPackage:
    intel = get_setting(session, "intelligence")
    share_names = (not for_cloud) or bool(intel.get("share_identity_names"))
    identities = []
    pseudonyms: dict[int, str] = {}
    for i, ident in enumerate(session.scalars(select(Identity)).all(), start=1):
        label = ident.display_name if share_names else f"Person {i}"
        pseudonyms[ident.id] = label
        entry: dict[str, Any] = {"id": ident.id, "name": label, "kind": ident.kind}
        if share_names:
            entry["aliases"] = [a.alias for a in ident.aliases]
        identities.append(entry)

    accounts = []
    for a in session.scalars(select(Account).where(Account.active.is_(True))).all():
        accounts.append(
            {
                "id": a.id,
                "name": a.name,
                "type": a.account_type,
                "institution": a.institution.name if a.institution else None,
                "currency": a.currency,
                "owners": [pseudonyms.get(o.identity_id) for o in a.owners],
            }
        )

    cats = {c.id: c.slug for c in session.scalars(select(Category)).all()}
    merchants = []
    mids = set(merchant_ids)
    keys = set(merchant_keys)
    if mids or keys:
        q = select(Merchant).where((Merchant.id.in_(mids)) | (Merchant.key.in_(keys)))
        for m in session.scalars(q).all():
            merchants.append(
                {
                    "name": m.canonical_name,
                    "default_category": cats.get(m.default_category_id),
                    "source": m.source,
                }
            )

    rules = [
        {"name": r.name, "if": r.conditions, "then": r.actions}
        for r in session.scalars(
            select(ClassificationRule).where(
                ClassificationRule.active.is_(True), ClassificationRule.source == "user"
            )
        ).all()
    ]

    examples = []
    q = (
        select(Transaction)
        .join(TransactionOverride, TransactionOverride.transaction_id == Transaction.id)
        .where(TransactionOverride.field == "category")
        .order_by(TransactionOverride.created_at.desc())
        .limit(max_examples)
    )
    for t in session.scalars(q).unique().all():
        examples.append(
            {
                "description": t.description_raw,
                "direction": t.direction,
                "category": t.category.slug if t.category else None,
            }
        )

    general = get_setting(session, "general")
    return ContextPackage(
        config_version=current_version(session),
        taxonomy=taxonomy_for_prompt(session),
        accounts=accounts,
        identities=identities,
        merchants=merchants,
        rules=rules,
        examples=examples,
        locale={
            "country": general.get("country"),
            "base_currency": general.get("base_currency"),
        },
    )
