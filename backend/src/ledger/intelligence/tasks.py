"""Application-level intelligence tasks: prompt construction + strict output validation.

Every task returns validated, typed data or raises; callers fall back to deterministic
behaviour when no provider is configured or all providers fail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ledger.intelligence.context import build_context
from ledger.intelligence.router import IntelligenceRouter, ProviderFactory

SYSTEM_BASE = (
    "You are the classification engine of a local personal-finance ledger. "
    "Interpret bank and credit-card transactions precisely. Use only the categories "
    "provided. Investments, transfers between own accounts and credit-card bill payments "
    "are NOT expenses. Answer with JSON only."
)


@dataclass
class TxnForAI:
    ref: int
    description: str
    amount: Decimal
    currency: str
    direction: str
    account_type: str
    txn_date: date
    merchant_hint: str | None = None


@dataclass
class AIClassification:
    ref: int
    category: str
    merchant: str | None
    confidence: float
    recurring: bool
    reason: str


def _cloud_in_chain(router: IntelligenceRouter, task: str) -> bool:
    return any(not c.is_local for c in router.chain(task))


def classify_transactions(
    session: Session,
    txns: list[TxnForAI],
    *,
    provider_factory: ProviderFactory | None = None,
) -> tuple[list[AIClassification], int | None]:
    router = IntelligenceRouter(session, provider_factory)
    ctx = build_context(
        session,
        for_cloud=_cloud_in_chain(router, "classify"),
        merchant_keys=[t.merchant_hint for t in txns if t.merchant_hint],
    )
    valid_slugs = {c["slug"] for c in ctx.taxonomy}
    payload = {
        "context": ctx.as_prompt_dict(),
        "transactions": [
            {
                "ref": t.ref,
                "date": t.txn_date.isoformat(),
                "description": t.description,
                "amount": str(abs(t.amount)),
                "currency": t.currency,
                "direction": t.direction,
                "account_type": t.account_type,
                "merchant_hint": t.merchant_hint,
            }
            for t in txns
        ],
        "output_schema": {
            "results": [
                {
                    "ref": "int (echo input ref)",
                    "category": "one taxonomy slug",
                    "merchant": "canonical merchant/counterparty name or null",
                    "confidence": "0..1",
                    "recurring": "bool",
                    "reason": "short justification",
                }
            ]
        },
    }
    user = (
        "Classify each transaction. Prefer user rules and corrected examples when they "
        'apply. Return {"results": [...]} with one entry per transaction.\n\n'
        + json.dumps(payload, default=str)
    )

    def validate(data: Any) -> list[AIClassification]:
        results = data["results"] if isinstance(data, dict) else data
        refs = {t.ref for t in txns}
        out = []
        for r in results:
            ref = int(r["ref"])
            slug = str(r["category"]).strip()
            if ref not in refs or slug not in valid_slugs:
                continue
            conf = float(r.get("confidence", 0.6))
            out.append(
                AIClassification(
                    ref=ref,
                    category=slug,
                    merchant=(str(r["merchant"]).strip()[:200] or None)
                    if r.get("merchant")
                    else None,
                    confidence=max(0.0, min(1.0, conf)),
                    recurring=bool(r.get("recurring", False)),
                    reason=str(r.get("reason", ""))[:300],
                )
            )
        if not out:
            raise ValueError("no valid classifications in model output")
        return out

    outcome = router.run("classify", SYSTEM_BASE, user, validate=validate, item_count=len(txns))
    return outcome.data, outcome.execution_id


def extract_rows_from_text(
    session: Session,
    page_text: str,
    *,
    is_card: bool,
    provider_factory: ProviderFactory | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """LLM fallback for documents the deterministic extractors could not parse."""
    router = IntelligenceRouter(session, provider_factory)
    user = (
        "Extract every transaction from this statement text. Return "
        '{"transactions": [{"date": "YYYY-MM-DD", "description": str, '
        '"amount": "decimal string, negative for money leaving the account", '
        '"balance": "decimal string or null", "reference": str|null}]}. '
        f"This is a {'credit card' if is_card else 'bank'} statement. Do not invent rows; "
        "skip summary/total lines.\n\n---\n" + page_text[:60_000]
    )

    def validate(data: Any) -> list[dict[str, Any]]:
        rows = data["transactions"]
        out = []
        for r in rows:
            date.fromisoformat(str(r["date"]))
            Decimal(str(r["amount"]))
            out.append(r)
        return out

    outcome = router.run(
        "extract",
        "You extract financial transactions from statements. JSON only.",
        user,
        validate=validate,
    )
    return outcome.data, outcome.execution_id


def adjudicate_match(
    session: Session,
    kind: str,
    source: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    provider_factory: ProviderFactory | None = None,
) -> tuple[int | None, float, str]:
    router = IntelligenceRouter(session, provider_factory)
    user = (
        f"Decide which candidate (if any) is the counterpart of this {kind.replace('_', ' ')}. "
        'Return {"candidate_id": int|null, "confidence": 0..1, "reason": str}.\n\n'
        + json.dumps({"transaction": source, "candidates": candidates}, default=str)
    )
    ids = {c["id"] for c in candidates}

    def validate(data: Any) -> tuple[int | None, float, str]:
        cid = data.get("candidate_id")
        if cid is not None and int(cid) not in ids:
            raise ValueError("unknown candidate")
        return (
            int(cid) if cid is not None else None,
            float(data.get("confidence", 0.5)),
            str(data.get("reason", ""))[:300],
        )

    return router.run("reconcile", SYSTEM_BASE, user, validate=validate).data


def answer_query(
    session: Session,
    question: str,
    facts: dict[str, Any],
    *,
    provider_factory: ProviderFactory | None = None,
) -> dict[str, Any]:
    router = IntelligenceRouter(session, provider_factory)
    user = (
        "Answer the user's question about their finances using ONLY the facts provided "
        "(pre-computed from their ledger). If the facts are insufficient, say what is "
        'missing. Return {"answer": str, "table": [[...]] | null}.\n\n'
        + json.dumps({"question": question, "facts": facts}, default=str)
    )

    def validate(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict) or "answer" not in data:
            raise ValueError("missing answer")
        return {"answer": str(data["answer"]), "table": data.get("table")}

    return router.run(
        "query", "You are a careful personal-finance analyst.", user, validate=validate
    ).data
