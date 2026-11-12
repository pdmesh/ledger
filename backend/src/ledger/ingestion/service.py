"""Document registration, identification, extraction and ledger insertion."""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger.classification.engine import Classifier, detect_recurring
from ledger.config import current_version, get_setting
from ledger.fx import apply_base_amount, base_currency
from ledger.identity import resolve_account_owners
from ledger.ingestion.extract import ExtractionError, detect_format, extract_statement
from ledger.ingestion.parsing import (
    ParsedRow,
    ParsedStatement,
    ParseOptions,
    StatementMetadata,
    parse_date,
)
from ledger.intelligence.router import IntelligenceRouter, NoProviderAvailable, ProviderFactory
from ledger.intelligence.tasks import extract_rows_from_text
from ledger.models import Account, Document, ImportBatch, Institution, Transaction
from ledger.settings import RuntimeSettings
from ledger.text import normalize_description

log = logging.getLogger(__name__)

ACCOUNT_TYPE_LABEL = {
    "savings": "Savings",
    "current": "Current",
    "credit_card": "Credit Card",
    "investment": "Investments",
    "brokerage": "Brokerage",
    "fixed_deposit": "Fixed Deposit",
    "loan": "Loan",
    "cash": "Cash",
    "other": "Account",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class RegisterResult:
    document: Document
    duplicate: bool


def new_batch(session: Session, source: str) -> ImportBatch:
    b = ImportBatch(source=source)
    session.add(b)
    session.flush()
    return b


def register_file(
    session: Session,
    rt: RuntimeSettings,
    src: Path,
    *,
    original_name: str | None = None,
    batch: ImportBatch | None = None,
    source_path: str | None = None,
) -> RegisterResult:
    """Copy a file into the archive (unmodified) and create its Document record.

    Idempotent: re-importing identical bytes returns the existing document.
    """
    digest = sha256_file(src)
    existing = session.scalar(select(Document).where(Document.sha256 == digest))
    if existing:
        return RegisterResult(existing, True)
    fmt = detect_format(src)
    name = original_name or src.name
    dest_dir = rt.archive_dir / digest[:2]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest}{Path(name).suffix.lower() or '.' + fmt}"
    if not dest.exists():
        shutil.copy2(src, dest)
    doc = Document(
        batch_id=batch.id if batch else None,
        sha256=digest,
        original_filename=name,
        source_path=source_path,
        archive_path=str(dest.relative_to(rt.data_dir)),
        file_format=fmt,
        size_bytes=dest.stat().st_size,
        status="queued",
    )
    session.add(doc)
    session.flush()
    return RegisterResult(doc, False)


def parse_options(session: Session) -> ParseOptions:
    g = get_setting(session, "general")
    fmt = g.get("date_format") or "auto"
    return ParseOptions(
        date_order=fmt if fmt in ("DMY", "MDY", "YMD") else "auto",
        decimal_sep=g.get("decimal_separator") or ".",
        default_currency=g.get("base_currency"),
        default_date_order="MDY" if g.get("country") == "US" else "DMY",
    )


def _known_institutions(session: Session) -> list[tuple[str, list[str]]]:
    return [(i.name, i.aliases or []) for i in session.scalars(select(Institution)).all()]


def _get_institution(session: Session, name: str | None) -> Institution | None:
    if not name:
        return None
    inst = session.scalar(select(Institution).where(Institution.name == name))
    if inst is None:
        inst = Institution(name=name, aliases=[])
        session.add(inst)
        session.flush()
    return inst


def resolve_account(
    session: Session, st: ParsedStatement, inst: Institution | None, default_ccy: str | None
) -> tuple[Account, bool]:
    md = st.metadata
    acct_type = md.account_type or "other"
    q = select(Account)
    candidates = list(session.scalars(q).all())

    def score(a: Account) -> int:
        s = 0
        if md.account_number_last4 and a.masked_number == md.account_number_last4:
            s += 4
        elif (
            md.account_number_last4
            and a.masked_number
            and a.masked_number != md.account_number_last4
        ):
            return -1
        if inst and a.institution_id == inst.id:
            s += 2
        elif inst and a.institution_id and a.institution_id != inst.id:
            return -1
        if a.account_type == acct_type:
            s += 1
        return s

    ranked = sorted(((score(a), a) for a in candidates), key=lambda x: -x[0])
    # need either a number match, or institution+type match with no number on either side
    if ranked and ranked[0][0] >= 4:
        return ranked[0][1], False
    if ranked and ranked[0][0] == 3 and not md.account_number_last4:
        return ranked[0][1], False

    label = ACCOUNT_TYPE_LABEL.get(acct_type, "Account")
    name = f"{inst.name if inst else 'Unknown'} {label}"
    if md.account_number_last4:
        name += f" ••{md.account_number_last4}"
    acct = Account(
        institution_id=inst.id if inst else None,
        name=name,
        account_type=acct_type,
        masked_number=md.account_number_last4,
        currency=md.currency or default_ccy or "XXX",
        aliases=[],
        statement_metadata={"document_type": md.document_type},
        auto_discovered=True,
    )
    session.add(acct)
    session.flush()
    return acct, True


def _fingerprint_base(account_id: int, r: ParsedRow) -> str:
    desc = normalize_description(r.description)
    return f"{account_id}|{r.txn_date.isoformat()}|{r.amount}|{desc}|{r.reference or ''}"


def _fingerprint(base: str, occurrence: int) -> str:
    return hashlib.sha256(f"{base}|{occurrence}".encode()).hexdigest()


def _llm_extract(
    session: Session, st: ParsedStatement, path: Path, pf: ProviderFactory | None
) -> None:
    from ledger.ingestion.pdf import read_pdf

    if not IntelligenceRouter(session, pf).available("extract"):
        st.warnings.append("No intelligence provider routed for 'extract'; cannot fall back")
        return
    text = (
        read_pdf(path).full_text
        if path.suffix.lower() == ".pdf"
        else path.read_text(errors="replace")
    )
    try:
        rows, _ = extract_rows_from_text(
            session, text, is_card=st.metadata.account_type == "credit_card", provider_factory=pf
        )
    except NoProviderAvailable as e:
        st.warnings.append(f"AI extraction failed: {e}")
        return
    for i, r in enumerate(rows):
        d = parse_date(r["date"], "YMD")
        if d is None:
            continue
        st.rows.append(
            ParsedRow(
                txn_date=d,
                description=str(r.get("description", "")),
                amount=Decimal(str(r["amount"])),
                balance=Decimal(str(r["balance"])) if r.get("balance") not in (None, "") else None,
                reference=r.get("reference"),
                source_ref={"llm_row": i},
                raw=r,
                sign_basis="llm",
            )
        )
    st.method = "llm"
    st.warnings.append("Transactions extracted by AI; verify against the original document")


def process_document(
    session: Session,
    rt: RuntimeSettings,
    doc: Document,
    *,
    provider_factory: ProviderFactory | None = None,
    use_ai: bool = True,
) -> dict[str, Any]:
    doc.status = "processing"
    session.flush()
    path = rt.data_dir / doc.archive_path
    opts = parse_options(session)
    err = ""
    st: ParsedStatement | None
    try:
        st = extract_statement(
            path,
            doc.file_format,
            opts,
            filename=doc.original_filename,
            known_institutions=_known_institutions(session),
        )
    except ExtractionError as e:
        st, err = None, str(e)
    if st is None or not st.rows:
        if st is None:
            st = ParsedStatement([], "", StatementMetadata(), "none", [err])
        if use_ai:
            _llm_extract(session, st, path, provider_factory)
        if not st.rows:
            doc.status = "failed"
            doc.error = "; ".join(st.warnings) or "No transactions found"
            doc.warnings = st.warnings
            return {"status": "failed", "error": doc.error}

    md = st.metadata
    base = base_currency(session)
    inst = _get_institution(session, md.institution)
    account, created = resolve_account(session, st, inst, opts.default_currency)
    owners = resolve_account_owners(session, account, md.holder_text, st.header_text)

    # ---- insert transactions with duplicate detection ---------------------------------
    occurrences: Counter[str] = Counter()
    new_txns: list[Transaction] = []
    dup_exact = dup_in_doc = 0
    prev: ParsedRow | None = None
    prev_txn: Transaction | None = None
    for r in st.rows:
        base_fp = _fingerprint_base(account.id, r)
        occurrences[base_fp] += 1
        fp = _fingerprint(base_fp, occurrences[base_fp])
        duplicate_of = None
        # identical row with identical running balance within the same document
        if (
            prev is not None
            and prev_txn is not None
            and _fingerprint_base(account.id, prev) == base_fp
            and r.balance is not None
            and prev.balance == r.balance
        ):
            duplicate_of = prev_txn.id
            dup_in_doc += 1
        if duplicate_of is None:
            existing = session.scalar(
                select(Transaction.id).where(
                    Transaction.fingerprint == fp,
                    Transaction.duplicate_of_id.is_(None),
                    Transaction.document_id != doc.id,
                )
            )
            if existing:
                duplicate_of = existing
                dup_exact += 1
        t = Transaction(
            account_id=account.id,
            document_id=doc.id,
            source_ref=r.source_ref,
            txn_date=r.txn_date,
            posting_date=r.posting_date,
            description_raw=r.description,
            description_normalized=normalize_description(r.description),
            amount=r.amount,
            currency=(r.currency or account.currency or base or "XXX"),
            direction="inflow" if r.amount > 0 else "outflow",
            reference=r.reference,
            balance_after=r.balance,
            raw={**r.raw, "sign_basis": r.sign_basis},
            fingerprint=fp,
            duplicate_of_id=duplicate_of,
        )
        t.account = account
        apply_base_amount(session, t, base)
        session.add(t)
        session.flush()
        new_txns.append(t)
        prev, prev_txn = r, t

    classifier = Classifier(session, use_ai=use_ai, provider_factory=provider_factory)
    cstats = classifier.classify([t for t in new_txns if t.duplicate_of_id is None])
    detect_recurring(session, {t.merchant_id for t in new_txns if t.merchant_id})

    # ---- document metadata ------------------------------------------------------------
    dates = [r.txn_date for r in st.rows]
    doc.institution_id = inst.id if inst else None
    doc.account_id = account.id
    doc.document_type = md.document_type
    doc.statement_start = md.period_start or (min(dates) if dates else None)
    doc.statement_end = md.period_end or (max(dates) if dates else None)
    doc.currency = md.currency or account.currency
    doc.opening_balance = md.opening_balance
    doc.closing_balance = md.closing_balance
    doc.extraction_method = st.method
    doc.warnings = st.warnings
    doc.identification = {
        "institution": md.institution,
        "account_type": md.account_type,
        "account_last4": md.account_number_last4,
        "holder_text": md.holder_text,
        # kept locally so later identity-alias changes can re-run ownership resolution
        "header_excerpt": (st.header_text or "")[:4000],
        "owners_matched": [{"identity_id": o.identity_id, "score": o.score} for o in owners],
        "account_created": created,
        "evidence": md.evidence,
    }
    doc.config_version = current_version(session)
    doc.stats = {
        "rows": len(st.rows),
        "inserted": len(new_txns),
        "duplicates_across_documents": dup_exact,
        "duplicates_within_document": dup_in_doc,
        "classification": cstats.as_dict(),
    }
    doc.status = "processed"
    doc.error = None
    session.flush()

    from ledger.reconciliation.engine import Reconciler

    window = (min(dates), max(dates)) if dates else (date.today(), date.today())
    recon = Reconciler(session, provider_factory=provider_factory, use_ai=use_ai).run(
        date_from=window[0], date_to=window[1]
    )
    doc.stats = {**doc.stats, "reconciliation": recon}
    session.flush()
    return {"status": "processed", **doc.stats}
