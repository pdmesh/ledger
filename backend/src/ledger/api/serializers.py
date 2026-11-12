"""Model -> JSON serialization (kept explicit so the frontend contract is obvious)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ledger.models import (
    Account,
    Category,
    ClassificationRule,
    Document,
    Identity,
    Merchant,
    ReconciliationLink,
    Transaction,
)


def money(v: Decimal | None) -> str | None:
    return None if v is None else str(v)


def identity(i: Identity) -> dict[str, Any]:
    return {
        "id": i.id,
        "display_name": i.display_name,
        "legal_name": i.legal_name,
        "kind": i.kind,
        "identifiers": i.identifiers or [],
        "aliases": [{"id": a.id, "alias": a.alias} for a in i.aliases],
    }


def account(a: Account) -> dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "institution_id": a.institution_id,
        "institution": a.institution.name if a.institution else None,
        "masked_number": a.masked_number,
        "currency": a.currency,
        "aliases": a.aliases or [],
        "auto_discovered": a.auto_discovered,
        "active": a.active,
        "owners": [
            {"identity_id": o.identity_id, "source": o.source, "confidence": o.confidence}
            for o in a.owners
        ],
    }


def category(c: Category) -> dict[str, Any]:
    return {
        "id": c.id,
        "slug": c.slug,
        "name": c.name,
        "description": c.description,
        "parent_id": c.parent_id,
        "role": c.role,
        "is_system": c.is_system,
        "active": c.active,
        "merged_into_id": c.merged_into_id,
        "semantic_version": c.semantic_version,
        "sort_order": c.sort_order,
    }


def merchant(m: Merchant, txn_count: int | None = None) -> dict[str, Any]:
    d = {
        "id": m.id,
        "canonical_name": m.canonical_name,
        "description": m.description,
        "default_category_id": m.default_category_id,
        "source": m.source,
        "aliases": [
            {"id": a.id, "pattern": a.pattern, "match_type": a.match_type, "source": a.source}
            for a in m.aliases
        ],
    }
    if txn_count is not None:
        d["transaction_count"] = txn_count
    return d


def rule(r: ClassificationRule) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "priority": r.priority,
        "conditions": r.conditions,
        "actions": r.actions,
        "source": r.source,
        "confidence": r.confidence,
        "active": r.active,
    }


def document(d: Document) -> dict[str, Any]:
    ident = dict(d.identification or {})
    ident.pop("header_excerpt", None)  # local-only evidence, not needed by the UI list
    return {
        "id": d.id,
        "original_filename": d.original_filename,
        "file_format": d.file_format,
        "size_bytes": d.size_bytes,
        "status": d.status,
        "error": d.error,
        "warnings": d.warnings or [],
        "institution": d.institution.name if d.institution else None,
        "account_id": d.account_id,
        "account": d.account.name if d.account else None,
        "document_type": d.document_type,
        "statement_start": d.statement_start,
        "statement_end": d.statement_end,
        "currency": d.currency,
        "opening_balance": money(d.opening_balance),
        "closing_balance": money(d.closing_balance),
        "extraction_method": d.extraction_method,
        "identification": ident,
        "stats": d.stats or {},
        "source_path": d.source_path,
        "created_at": d.created_at,
    }


def transaction(t: Transaction) -> dict[str, Any]:
    return {
        "id": t.id,
        "account_id": t.account_id,
        "account": t.account.name if t.account else None,
        "account_type": t.account.account_type if t.account else None,
        "document_id": t.document_id,
        "txn_date": t.txn_date,
        "posting_date": t.posting_date,
        "description_raw": t.description_raw,
        "amount": money(t.amount),
        "currency": t.currency,
        "base_amount": money(t.base_amount),
        "direction": t.direction,
        "reference": t.reference,
        "balance_after": money(t.balance_after),
        "category_id": t.category_id,
        "category": t.category.name if t.category else None,
        "role": t.category.role if t.category else None,
        "merchant_id": t.merchant_id,
        "merchant": t.merchant.canonical_name if t.merchant else None,
        "owner_identity_id": t.owner_identity_id,
        "is_recurring": t.is_recurring,
        "classification_method": t.classification_method,
        "classification_confidence": t.classification_confidence,
        "pinned_fields": t.pinned_fields or [],
        "duplicate_of_id": t.duplicate_of_id,
        "entry_method": t.entry_method,
    }


def link(lk: ReconciliationLink) -> dict[str, Any]:
    return {
        "id": lk.id,
        "kind": lk.kind,
        "from_transaction_id": lk.from_transaction_id,
        "to_transaction_id": lk.to_transaction_id,
        "confidence": lk.confidence,
        "method": lk.method,
        "evidence": lk.evidence,
        "status": lk.status,
        "history": lk.history,
        "created_at": lk.created_at,
    }
