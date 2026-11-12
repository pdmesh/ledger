"""Format dispatch: turn any supported file into a ``ParsedStatement``."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path

from ledger.ingestion.metadata import detect_metadata
from ledger.ingestion.parsing import ParsedRow, ParsedStatement, ParseOptions
from ledger.ingestion.pdf import extract_from_lines, extract_from_tables, read_pdf
from ledger.ingestion.tabular import (
    detect_header,
    extract_rows,
    read_csv,
    read_xls,
    read_xlsx,
    rows_to_text,
)

SUPPORTED_FORMATS = {
    ".csv": "csv",
    ".tsv": "csv",
    ".txt": "csv",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xls": "xls",
    ".pdf": "pdf",
}


class ExtractionError(Exception):
    pass


def detect_format(path: Path) -> str:
    fmt = SUPPORTED_FORMATS.get(path.suffix.lower())
    head = path.read_bytes()[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK"):
        return "xlsx"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    if fmt is None:
        raise ExtractionError(f"Unsupported file type: {path.suffix or 'unknown'}")
    return fmt


def extract_statement(
    path: Path,
    fmt: str,
    opts: ParseOptions,
    *,
    filename: str = "",
    known_institutions: Iterable[tuple[str, list[str]]] = (),
    pdf_password: str | None = None,
) -> ParsedStatement:
    known_institutions = list(known_institutions)
    order_hint = opts.date_order if opts.date_order != "auto" else opts.default_date_order

    if fmt in ("csv", "xlsx", "xls"):
        if fmt == "csv":
            sheets = [("csv", read_csv(path))]
        elif fmt == "xlsx":
            sheets = read_xlsx(path)
        else:
            sheets = read_xls(path)
        all_rows: list[ParsedRow] = []
        warnings: list[str] = []
        header_text = ""
        for sheet_name, rows in sheets:
            cm = detect_header(rows)
            if cm is None:
                continue
            header_text += rows_to_text(rows[: cm.header_row]) + "\n"
            md = detect_metadata(
                header_text,
                date_order=order_hint,
                filename=filename,
                known_institutions=known_institutions,
            )
            is_card = md.account_type == "credit_card"
            ref = {"sheet": sheet_name} if fmt != "csv" else {}
            r, w = extract_rows(rows, cm, opts, is_card=is_card, ref_prefix=ref)
            all_rows.extend(r)
            warnings.extend(w)
        if not all_rows and not header_text:
            raise ExtractionError("No transaction table found (date/description/amount columns)")
        md = detect_metadata(
            header_text,
            date_order=order_hint,
            filename=filename,
            known_institutions=known_institutions,
        )
        st = ParsedStatement(all_rows, header_text, md, f"tabular:{fmt}", warnings)
    elif fmt == "pdf":
        pdf = read_pdf(path, pdf_password)
        text = pdf.full_text
        if not text.strip():
            raise ExtractionError(
                "PDF has no text layer (scanned image). OCR is not yet enabled for this file."
            )
        first = "\n".join(pdf.pages[:2])
        md = detect_metadata(
            first, date_order=order_hint, filename=filename, known_institutions=known_institutions
        )
        is_card = md.account_type == "credit_card"
        rows, warnings = extract_from_tables(pdf, opts, is_card=is_card)
        method = "pdf:tables"
        if not rows:
            rows, warnings = extract_from_lines(
                pdf, opts, is_card=is_card, opening_balance=md.opening_balance
            )
            method = "pdf:lines"
        st = ParsedStatement(rows, first, md, method, warnings)
    else:  # pragma: no cover
        raise ExtractionError(f"Unsupported format {fmt}")

    _post_validate(st)
    return st


def _post_validate(st: ParsedStatement) -> None:
    md = st.metadata
    if not st.rows:
        st.warnings.append("No transactions were extracted")
        return
    dates = [r.txn_date for r in st.rows]
    if md.period_start is None:
        md.period_start = min(dates)
    if md.period_end is None:
        md.period_end = max(dates)
    out_of_period = [d for d in dates if d < md.period_start or d > md.period_end]
    if out_of_period:
        st.warnings.append(f"{len(out_of_period)} transaction(s) fall outside the statement period")
    if (
        md.opening_balance is not None
        and md.closing_balance is not None
        and md.account_type != "credit_card"
    ):
        total = sum((r.amount for r in st.rows), Decimal(0))
        expected = md.closing_balance - md.opening_balance
        md.evidence["balance_check"] = {
            "opening": str(md.opening_balance),
            "closing": str(md.closing_balance),
            "sum": str(total),
            "ok": total == expected,
        }
        if total != expected:
            st.warnings.append(
                f"Statement totals do not reconcile: opening {md.opening_balance} + "
                f"transactions {total} != closing {md.closing_balance}"
            )
    # running balance chain check
    breaks = 0
    for prev, cur in zip(st.rows, st.rows[1:], strict=False):
        if prev.balance is not None and cur.balance is not None:
            if (
                prev.balance + cur.amount != cur.balance
                and cur.balance + prev.amount != prev.balance
            ):
                breaks += 1
    if breaks:
        st.warnings.append(f"Running balance does not chain on {breaks} row(s)")
