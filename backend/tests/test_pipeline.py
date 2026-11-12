from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from ledger.analytics.service import Filters, overview
from ledger.ingestion.service import register_file
from ledger.jobs import enqueue, run_pending
from ledger.models import Account, Document, ReconciliationLink, Transaction

from .conftest import FIXTURES

FILES = [
    "northwind_savings_2026-01.csv",
    "contoso_savings_2026-01.xlsx",
    "fabrikam_card_2026-01.pdf",
]


def import_files(db, rt, names):
    with db.session() as s:
        for n in names:
            res = register_file(s, rt, FIXTURES / n)
            if not res.duplicate:
                enqueue(s, "process_document", {"document_id": res.document.id})
    run_pending(db, rt)


def by_desc(s, needle):
    return s.scalars(select(Transaction).where(Transaction.description_raw.contains(needle))).all()


def test_end_to_end(db, rt, household):
    import_files(db, rt, FILES)
    with db.session() as s:
        docs = s.scalars(select(Document)).all()
        assert [d.status for d in docs] == ["processed"] * 3, [d.error for d in docs]
        accts = {a.masked_number: a for a in s.scalars(select(Account)).all()}
        assert set(accts) == {"4321", "8765", "9988"}
        assert accts["9988"].account_type == "credit_card"
        assert accts["4321"].institution.name == "Northwind Bank"
        # ownership resolved from statement header, not guessed per transaction
        assert [o.identity_id for o in accts["4321"].owners] == [household["Alex Sample"]]
        assert [o.identity_id for o in accts["8765"].owners] == [household["Sam Sample"]]

        cat = lambda needle: by_desc(s, needle)[0].category.slug  # noqa: E731
        assert cat("SALARY JAN 2026") == "salary"
        assert cat("MUTUAL FUND SIP") == "mutual-fund-purchase"
        assert cat("ATM WDL") == "cash-withdrawal"
        assert cat("INTEREST CREDIT") == "interest"
        # reconciliation
        assert cat("IMPS-TRF TO OWN AC") == "internal-transfer"
        assert cat("IMPS FROM ALEX") == "internal-transfer"
        assert cat("CC PAYMENT FABRIKAM") == "card-settlement"
        assert cat("PAYMENT RECEIVED") == "card-settlement"
        assert cat("REFUND AMAZON") == "refund"
        kinds = sorted(lk.kind for lk in s.scalars(select(ReconciliationLink)).all())
        assert kinds == ["card_settlement", "internal_transfer", "refund"]

        # merchant normalization across formats: UPI handle + card descriptor
        swiggy = {t.merchant.canonical_name for t in by_desc(s, "SWIGGY")}
        assert swiggy == {"Swiggy"}, swiggy

        ov = overview(s, Filters())["metrics"]
        # settlement (30,000) and transfer (20,000) are not consumption or income
        assert Decimal(ov["income"]) == Decimal("240250.00")
        consumption = Decimal(ov["consumption"])
        assert Decimal(ov["transfers"]) >= Decimal("50000")
        # card purchases count once; refund reduces consumption
        card_purchases = Decimal("1200") + Decimal("18000") + Decimal("800") + Decimal("649")
        bank_spend = (
            Decimal("450") + Decimal("620") + Decimal("25000") + Decimal("3200") + Decimal("2100")
        )
        assert consumption == card_purchases + bank_spend - Decimal("2000")
        assert Decimal(ov["investment_outflows"]) == Decimal("10000")


def test_reimport_is_idempotent_and_overlaps_dedupe(db, rt, household):
    import_files(db, rt, FILES)
    import_files(db, rt, FILES)  # identical bytes -> no new docs
    with db.session() as s:
        assert len(s.scalars(select(Document)).all()) == 3
        before = len(
            s.scalars(select(Transaction).where(Transaction.duplicate_of_id.is_(None))).all()
        )
    import_files(db, rt, ["northwind_savings_2026-01-15_to_02-10.csv"])
    with db.session() as s:
        live = s.scalars(select(Transaction).where(Transaction.duplicate_of_id.is_(None))).all()
        dups = s.scalars(select(Transaction).where(Transaction.duplicate_of_id.is_not(None))).all()
        assert len(dups) == 4  # four overlapping rows kept for provenance but flagged
        overlap = s.scalars(select(Document).order_by(Document.id.desc())).first()
        assert overlap.stats["duplicates_across_documents"] == 4  # exact fingerprint matches
        assert len(live) == before + 2  # Feb salary + Feb swiggy
        feb_salary = by_desc(s, "SALARY FEB")[0]
        assert feb_salary.category.slug == "salary"
        assert feb_salary.account.masked_number == "4321"
