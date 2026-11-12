"""Header-detecting extractor for tabular statements (CSV, XLSX, XLS and PDF tables)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from ledger.ingestion.parsing import (
    ParsedRow,
    ParseOptions,
    infer_date_order,
    parse_amount,
    parse_date,
)

SYNONYMS: dict[str, tuple[str, ...]] = {
    "date": (
        "transaction date",
        "txn date",
        "tran date",
        "trans date",
        "date",
        "booking date",
        "posted date",
        "value dt",
        "date of transaction",
    ),
    "posting_date": ("value date", "posting date", "post date", "settlement date", "value dt"),
    "description": (
        "description",
        "narration",
        "particulars",
        "details",
        "transaction details",
        "remarks",
        "transaction remarks",
        "merchant",
        "payee",
        "memo",
        "transaction description",
        "transaction particulars",
    ),
    "debit": (
        "debit",
        "withdrawal",
        "withdrawals",
        "withdrawal amt",
        "withdrawal amount",
        "debit amount",
        "dr",
        "debits",
        "amount debited",
        "paid out",
        "money out",
    ),
    "credit": (
        "credit",
        "deposit",
        "deposits",
        "deposit amt",
        "deposit amount",
        "credit amount",
        "cr",
        "credits",
        "amount credited",
        "paid in",
        "money in",
    ),
    "amount": (
        "amount",
        "transaction amount",
        "amt",
        "amount (inr)",
        "amount(inr)",
        "value",
        "billing amount",
    ),
    "type": ("dr/cr", "cr/dr", "type", "transaction type", "debit/credit", "txn type"),
    "balance": (
        "balance",
        "closing balance",
        "running balance",
        "available balance",
        "balance amount",
        "balance (inr)",
    ),
    "reference": (
        "reference",
        "ref no",
        "ref",
        "chq/ref no",
        "chq no",
        "cheque no",
        "reference no",
        "ref no./cheque no.",
        "chq./ref.no.",
        "transaction id",
        "utr",
    ),
    "currency": ("currency", "ccy", "txn currency"),
}


def _norm_header(v: Any) -> str:
    s = re.sub(r"\s+", " ", str(v or "").strip().lower())
    return s.strip(" :.")


_NORMALIZED_SYNONYMS = {f: tuple(_norm_header(n) for n in names) for f, names in SYNONYMS.items()}


def _match_field(header: str) -> str | None:
    if not header:
        return None
    for fld, names in _NORMALIZED_SYNONYMS.items():
        if header in names:
            return fld
    # fuzzy: header starts with a synonym ("withdrawal amt (inr)")
    for fld, names in SYNONYMS.items():
        for n in names:
            if len(n) > 3 and (header.startswith(n) or n in header.split(" (")[0]):
                return fld
    return None


@dataclass
class ColumnMap:
    header_row: int
    columns: dict[str, int]
    width: int

    def has_amounts(self) -> bool:
        c = self.columns
        return "amount" in c or "debit" in c or "credit" in c


def detect_header(rows: list[list[Any]], scan: int = 60) -> ColumnMap | None:
    best: ColumnMap | None = None
    best_score = 0
    for i, row in enumerate(rows[:scan]):
        cols: dict[str, int] = {}
        for j, cell in enumerate(row):
            fld = _match_field(_norm_header(cell))
            if not fld:
                continue
            # first "date" column is the txn date, a second one becomes posting date
            if fld == "date" and "date" in cols:
                fld = "posting_date"
            if fld == "posting_date" and "date" not in cols and "posting_date" not in cols:
                # value date might be the only date column
                pass
            cols.setdefault(fld, j)
        if "date" not in cols and "posting_date" in cols:
            cols["date"] = cols.pop("posting_date")
        cm = ColumnMap(i, cols, len(row))
        if "date" in cols and "description" in cols and cm.has_amounts():
            score = len(cols)
            if score > best_score:
                best, best_score = cm, score
    return best


def _cell(row: list[Any], idx: int | None) -> Any:
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    if isinstance(v, str):
        v = v.strip()
    return v


def extract_rows(
    rows: list[list[Any]],
    colmap: ColumnMap,
    opts: ParseOptions,
    *,
    is_card: bool,
    ref_prefix: dict[str, Any] | None = None,
    start_row: int | None = None,
) -> tuple[list[ParsedRow], list[str]]:
    """Convert table rows into signed ``ParsedRow`` objects."""
    c = colmap.columns
    warnings: list[str] = []
    body = rows[(colmap.header_row + 1) if start_row is None else start_row :]
    order = opts.date_order
    if order == "auto":
        samples = [str(_cell(r, c["date"]) or "") for r in body[:200]]
        order = infer_date_order(samples, opts.default_date_order)

    out: list[ParsedRow] = []
    saw_minus = False  # a signed amount column: unsigned values are then inflows
    pending_desc_row: ParsedRow | None = None
    for offset, row in enumerate(body):
        row_no = (colmap.header_row + 1 if start_row is None else start_row) + offset
        if not any(str(x or "").strip() for x in row):
            continue
        d = parse_date(_cell(row, c["date"]), order)
        desc = str(_cell(row, c.get("description")) or "").strip()
        if d is None:
            # continuation line of a wrapped description
            if (
                pending_desc_row is not None
                and desc
                and not any(
                    parse_amount(_cell(row, c.get(k))) for k in ("amount", "debit", "credit")
                )
            ):
                pending_desc_row.description = f"{pending_desc_row.description} {desc}".strip()
            continue

        amount: Decimal | None = None
        basis = "column"
        if "debit" in c or "credit" in c:
            dr = parse_amount(_cell(row, c.get("debit")), opts.decimal_sep)
            cr = parse_amount(_cell(row, c.get("credit")), opts.decimal_sep)
            if dr and dr.value:
                amount = -dr.value
            elif cr and cr.value:
                amount = cr.value
            elif "amount" not in c:
                continue
        if amount is None and "amount" in c:
            pa = parse_amount(_cell(row, c["amount"]), opts.decimal_sep)
            if pa is None or pa.value == 0:
                continue
            ind = str(_cell(row, c.get("type")) or "").strip().lower()
            if ind in ("cr", "credit", "c", "+") or ind.startswith("cr"):
                amount, basis = pa.value, "indicator"
            elif ind in ("dr", "debit", "d", "-") or ind.startswith("dr") or ind.startswith("deb"):
                amount, basis = -pa.value, "indicator"
            elif pa.indicator:
                amount, basis = pa.value * pa.explicit_sign, "indicator"
            elif is_card:
                # Card exports disagree on polarity (charges +ve vs -ve); resolved per
                # document after all rows are read, see _resolve_card_polarity.
                amount = pa.value * (pa.explicit_sign or 1)
                basis = "card_signed"
            elif pa.explicit_sign:
                amount = pa.value * pa.explicit_sign
                saw_minus = saw_minus or pa.explicit_sign < 0
            else:
                # unsigned bank amount: resolved from the running balance when available
                amount, basis = pa.value, "convention"
        if amount is None:
            continue
        bal = parse_amount(_cell(row, c.get("balance")), opts.decimal_sep)
        balance = None
        if bal:
            balance = bal.value * (-1 if bal.explicit_sign < 0 else 1)
        posting = parse_date(_cell(row, c.get("posting_date")), order)
        raw = {f: (str(_cell(row, i)) if _cell(row, i) is not None else None) for f, i in c.items()}
        pr = ParsedRow(
            txn_date=d,
            posting_date=posting if posting != d else None,
            description=desc,
            amount=amount,
            currency=(str(_cell(row, c.get("currency")) or "").upper()[:3] or None),
            reference=(str(_cell(row, c.get("reference")) or "").strip() or None),
            balance=balance,
            source_ref={**(ref_prefix or {}), "row": row_no + 1},
            raw=raw,
            sign_basis=basis,
        )
        out.append(pr)
        pending_desc_row = pr

    if saw_minus:
        for r in out:
            if r.sign_basis == "convention":
                r.sign_basis = "column"
    if out and "balance" in c:
        _fix_signs_from_balance(out, warnings)
    elif any(r.sign_basis == "convention" for r in out):
        n = sum(1 for r in out if r.sign_basis == "convention")
        warnings.append(f"{n} amount(s) had no debit/credit indicator; assumed inflow")
    _resolve_card_polarity(out)
    return out, warnings


def _resolve_card_polarity(rows: list[ParsedRow]) -> None:
    """On card statements most rows are charges: the majority sign means 'outflow'."""
    signed = [r for r in rows if r.sign_basis == "card_signed"]
    if not signed:
        return
    positives = sum(1 for r in signed if r.amount > 0)
    flip = positives >= len(signed) - positives  # charges are positive -> make them negative
    for r in signed:
        if flip:
            r.amount = -r.amount
        r.sign_basis = "card_polarity"


def _fix_signs_from_balance(rows: list[ParsedRow], warnings: list[str]) -> None:
    """Use running balances to resolve unsigned amounts (and detect reversed ordering)."""
    candidates = [r for r in rows if r.sign_basis == "convention"]
    if not candidates:
        return
    fixed = 0
    for prev, cur in zip(rows, rows[1:], strict=False):
        if prev.balance is None or cur.balance is None or cur.sign_basis != "convention":
            continue
        delta = cur.balance - prev.balance
        if abs(delta) == abs(cur.amount):
            cur.amount = delta
            cur.sign_basis = "balance"
            fixed += 1
        elif (
            abs(prev.balance - cur.balance) == abs(prev.amount) and prev.sign_basis == "convention"
        ):
            # newest-first ordering
            prev.amount = prev.balance - cur.balance
            prev.sign_basis = "balance"
            fixed += 1
    unresolved = sum(1 for r in rows if r.sign_basis == "convention")
    if unresolved:
        warnings.append(
            f"{unresolved} amount(s) had no debit/credit indicator; assumed inflow by convention"
        )


# --------------------------------------------------------------------------------------
# File readers
# --------------------------------------------------------------------------------------


def read_csv(path: Path) -> list[list[Any]]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        text = raw.decode("utf-8", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)]


def read_xlsx(path: Path) -> list[tuple[str, list[list[Any]]]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        sheets.append((ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
    wb.close()
    return sheets


def read_xls(path: Path) -> list[tuple[str, list[list[Any]]]]:
    import xlrd

    book = xlrd.open_workbook(str(path))
    sheets = []
    for sh in book.sheets():
        rows = []
        for r in range(sh.nrows):
            vals = []
            for cidx in range(sh.ncols):
                cell = sh.cell(r, cidx)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    vals.append(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
                else:
                    vals.append(cell.value)
            rows.append(vals)
        sheets.append((sh.name, rows))
    return sheets


def rows_to_text(rows: list[list[Any]]) -> str:
    return "\n".join(" ".join(str(c) for c in r if c not in (None, "")) for r in rows)
