from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ledger.classification.engine import Classifier
from ledger.config import put_setting
from ledger.intelligence.providers import Provider, ProviderResult, extract_json
from ledger.intelligence.router import IntelligenceRouter
from ledger.models import Account, AIExecution, Merchant, Transaction


class FakeProvider(Provider):
    calls: list[str] = []

    def complete_json(self, system, user):
        FakeProvider.calls.append(user)
        payload = json.loads(user.split("\n\n", 1)[1])
        results = [
            {
                "ref": t["ref"],
                "category": "entertainment",
                "merchant": "Gamezone Arcade",
                "confidence": 0.82,
                "recurring": False,
                "reason": "arcade",
            }
            for t in payload["transactions"]
        ]
        return ProviderResult(
            data={"results": results},
            text="",
            model="fake-1",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0,
        )


def configure(s, allow_cloud, kind="local"):
    put_setting(
        s,
        "intelligence",
        {
            "providers": [{"id": "p1", "kind": kind, "model": "fake"}],
            "routing": {"default": ["p1"]},
            "allow_cloud": allow_cloud,
        },
    )


def make_txn(s, desc="GMZ*ARC 99812 PLAZA"):
    acct = Account(name="Test", account_type="savings", currency="INR")
    s.add(acct)
    s.flush()
    t = Transaction(
        account_id=acct.id,
        txn_date=date(2026, 1, 3),
        description_raw=desc,
        amount=Decimal("-300"),
        currency="INR",
        direction="outflow",
        fingerprint="x",
    )
    t.account = acct
    s.add(t)
    s.flush()
    return t


def test_llm_classification_with_provenance(db):
    with db.session() as s:
        configure(s, allow_cloud=False, kind="local")
        t = make_txn(s)
        stats = Classifier(s, provider_factory=FakeProvider).classify([t])
        assert stats.by_method["llm"] == 1
        assert t.category.slug == "entertainment"
        assert t.classification_method == "llm"
        assert t.merchant.canonical_name == "Gamezone Arcade"
        ex = s.scalars(select(AIExecution)).one()
        assert ex.status == "ok" and ex.model == "fake-1" and ex.item_count == 1
        # the merchant decision is reused next time without another model call
        FakeProvider.calls.clear()
        t2 = make_txn(s, "GMZ*ARC 55555 PLAZA")
        Classifier(s, provider_factory=FakeProvider).classify([t2])
        assert FakeProvider.calls == []
        assert t2.classification_method == "history"


def test_cloud_provider_blocked_without_opt_in(db):
    with db.session() as s:
        configure(s, allow_cloud=False, kind="api")
        assert not IntelligenceRouter(s, FakeProvider).available("classify")
        t = make_txn(s)
        Classifier(s, provider_factory=FakeProvider).classify([t])
        assert t.classification_method == "fallback"
        configure(s, allow_cloud=True, kind="api")
        assert IntelligenceRouter(s, FakeProvider).available("classify")


def test_cloud_prompt_pseudonymizes_names(db, household):
    from ledger.intelligence.context import build_context

    with db.session() as s:
        ctx = build_context(s, for_cloud=True)
        assert "Alex Sample" not in json.dumps(ctx.as_prompt_dict())
        ctx = build_context(s, for_cloud=False)
        assert "Alex Sample" in json.dumps(ctx.as_prompt_dict())


def test_invalid_model_output_falls_back(db):
    class Garbage(Provider):
        def complete_json(self, system, user):
            return ProviderResult(data={"results": [{"ref": 1, "category": "not-a-slug"}]}, text="")

    with db.session() as s:
        configure(s, allow_cloud=False)
        t = make_txn(s)
        Classifier(s, provider_factory=Garbage).classify([t])
        assert t.classification_method == "fallback"
        assert s.scalars(select(AIExecution)).one().status == "invalid_output"
        assert s.scalars(select(Merchant)).first() is not None


def test_extract_json_tolerates_fences():
    assert extract_json('Sure!\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert extract_json('prefix {"a": "}"} suffix') == {"a": "}"}


class FakeExtractor(Provider):
    def complete_json(self, system, user):
        rows = [
            {"date": "2026-01-03", "description": "SHOP", "amount": "-120.50", "balance": None},
            {"date": "2026-03-30", "description": "LATE", "amount": "-10", "balance": None},
        ]
        return ProviderResult(data={"transactions": rows}, text="", model="fake-x")


def test_ai_extraction_replaces_no_rows_warning(db, tmp_path):
    from ledger.ingestion.extract import NO_ROWS_WARNING, post_validate
    from ledger.ingestion.parsing import ParsedStatement, StatementMetadata
    from ledger.ingestion.service import _llm_extract

    src = tmp_path / "statement.txt"
    src.write_text("01/03 SHOP 120.50")
    md = StatementMetadata()
    md.period_start, md.period_end = date(2026, 1, 1), date(2026, 1, 31)
    st = ParsedStatement([], "", md, "pdf:lines", [])
    post_validate(st)
    assert st.warnings == [NO_ROWS_WARNING]
    with db.session() as s:
        configure(s, allow_cloud=True)
        _llm_extract(s, st, src, lambda cfg: FakeExtractor(cfg))
    assert len(st.rows) == 2 and st.method == "llm"
    assert NO_ROWS_WARNING not in st.warnings
    # validation now runs on the AI rows: the March row is outside the January period
    assert "1 transaction(s) fall outside the statement period" in st.warnings
