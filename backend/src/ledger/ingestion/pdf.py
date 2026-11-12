"""PDF statement extraction: table extraction first, then a line-pattern fallback."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from ledger.ingestion.parsing import (
    DATE_TOKEN,
    ParsedRow,
    ParseOptions,
    infer_date_order,
    parse_amount,
    parse_date,
)
from ledger.ingestion.tabular import ColumnMap, detect_header, extract_rows

_AMT = r"[\-(]?(?:[₹$€£]\s?)?\d{1,3}(?:[,\s]?\d{2,3})*(?:[.,]\d{2})\)?(?:\s?(?:Cr|Dr|CR|DR|cr|dr))?"
_LINE = re.compile(
    rf"^(?P<date>{DATE_TOKEN.pattern})\s+(?:(?P<date2>{DATE_TOKEN.pattern})\s+)?"
    rf"(?P<desc>.+?)\s+(?P<a1>{_AMT})(?:\s+(?P<a2>{_AMT}))?(?:\s+(?P<a3>{_AMT}))?\s*$"
)


class PdfText:
    def __init__(self, pages: list[str], tables: list[tuple[int, list[list[Any]]]]):
        self.pages = pages
        self.tables = tables

    @property
    def full_text(self) -> str:
        return "\n".join(self.pages)


def read_pdf(path: Path, password: str | None = None) -> PdfText:
    import pdfplumber

    pages: list[str] = []
    tables: list[tuple[int, list[list[Any]]]] = []
    with pdfplumber.open(str(path), password=password or "") as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            pages.append(page.extract_text() or "")
            try:
                for t in page.extract_tables():
                    if t and len(t) > 1:
                        tables.append((pno, t))
            except Exception:  # pragma: no cover - pdfplumber edge cases
                continue
    return PdfText(pages, tables)


def extract_from_tables(
    pdf: PdfText, opts: ParseOptions, *, is_card: bool
) -> tuple[list[ParsedRow], list[str]]:
    rows: list[ParsedRow] = []
    warnings: list[str] = []
    last_map: ColumnMap | None = None
    for t_index, (pno, table) in enumerate(pdf.tables):
        cm = detect_header(table, scan=8)
        start = None
        if cm is None and last_map is not None and len(table[0]) == last_map.width:
            cm, start = last_map, 0  # continuation table on a later page without header
        if cm is None:
            continue
        last_map = cm
        r, w = extract_rows(
            table,
            cm,
            opts,
            is_card=is_card,
            ref_prefix={"page": pno, "table": t_index},
            start_row=start,
        )
        rows.extend(r)
        warnings.extend(w)
    return rows, warnings


def extract_from_lines(
    pdf: PdfText,
    opts: ParseOptions,
    *,
    is_card: bool,
    opening_balance: Decimal | None = None,
) -> tuple[list[ParsedRow], list[str]]:
    """Regex fallback for text-layout statements without detectable tables."""
    warnings: list[str] = []
    candidates: list[tuple[int, int, re.Match[str]]] = []
    for pno, text in enumerate(pdf.pages, start=1):
        for lno, line in enumerate(text.splitlines(), start=1):
            m = _LINE.match(line.strip())
            if m:
                candidates.append((pno, lno, m))
    order = opts.date_order
    if order == "auto":
        order = infer_date_order(
            [m.group("date") for _, _, m in candidates], opts.default_date_order
        )

    rows: list[ParsedRow] = []
    prev_balance = opening_balance
    for pno, lno, m in candidates:
        d = parse_date(m.group("date"), order)
        if d is None:
            continue
        amounts = [parse_amount(m.group(k), opts.decimal_sep) for k in ("a1", "a2", "a3")]
        amounts = [a for a in amounts if a is not None]
        if not amounts:
            continue
        balance = None
        basis = "indicator"
        if len(amounts) == 1 or is_card:
            amt = amounts[0]
            if amt.explicit_sign:
                # on card statements "Cr" marks payments/refunds
                value = amt.value * amt.explicit_sign
            else:
                value = -amt.value if is_card else amt.value
                basis = "convention"
        else:
            bal_pa = amounts[-1]
            balance = bal_pa.value * (-1 if bal_pa.explicit_sign < 0 else 1)
            txn_amounts = [a for a in amounts[:-1] if a.value != 0]
            amt = txn_amounts[0] if txn_amounts else amounts[0]
            if amt.explicit_sign:
                value = amt.value * amt.explicit_sign
            elif prev_balance is not None and abs(balance - prev_balance) == amt.value:
                value = balance - prev_balance
                basis = "balance"
            elif len(amounts) == 3:
                # withdrawal, deposit, balance layout
                value = -amounts[0].value if amounts[0].value else amounts[1].value
                basis = "column"
            else:
                value = amt.value
                basis = "convention"
            prev_balance = balance
        rows.append(
            ParsedRow(
                txn_date=d,
                posting_date=parse_date(m.group("date2"), order) if m.group("date2") else None,
                description=m.group("desc").strip(),
                amount=value,
                balance=balance,
                source_ref={"page": pno, "line": lno},
                raw={"line": m.group(0)},
                sign_basis=basis,
            )
        )
    unresolved = sum(1 for r in rows if r.sign_basis == "convention")
    if unresolved and not is_card:
        warnings.append(f"{unresolved} PDF row(s) had an ambiguous sign; assumed inflow")
    return rows, warnings
