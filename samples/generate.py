#!/usr/bin/env python
"""Generate synthetic bank statements in many layouts, each with a ground-truth file.

Everything here is fake: merchants, references and names (e.g. "JANE DOE") are invented. The
output is safe to commit and to use for public demos.

For every layout this writes:
    synthetic/<layout>.<csv|tsv|xlsx>   the statement as a bank might export it
    synthetic/<layout>.truth.json       header, correct ColumnMapping, expected transactions

Usage:
    python samples/generate.py              # regenerate everything (deterministic)
    python samples/generate.py --list       # list layouts
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent / "synthetic"

# (narration template, min, max, direction) - direction +1 credit, -1 debit
MERCHANTS: list[tuple[str, int, int, int]] = [
    ("UPI/{ref}/SWIGGY/{handle}@okexample/Payment", 120, 900, -1),
    ("UPI/{ref}/ZEPTO MARKETPLACE/{handle}@ybl", 200, 2500, -1),
    ("POS {card} AMAZON MKTPLACE SEATTLE", 300, 6000, -1),
    ("POS {card} SHELL FUEL STATION 22", 1500, 4000, -1),
    ("ACH DEBIT NETFLIX.COM {ref}", 499, 649, -1),
    ("ATM WDL {ref} MG ROAD BRANCH", 2000, 10000, -1),
    ("IMPS-{ref}-JANE DOE-RENT", 15000, 15000, -1),
    ("NEFT DR-{ref}-CITY POWER UTILITY", 800, 3000, -1),
    ("CARD {card} UBER TRIP HELP.UBER.COM", 150, 700, -1),
    ("BIL/ONL/{ref}/ACME TELECOM POSTPAID", 399, 999, -1),
    ("SIP {ref} EXAMPLE MUTUAL FUND", 5000, 5000, -1),
    ("CHQ PAID {ref} JOHN Q PUBLIC", 1000, 8000, -1),
    ("NEFT CR-{ref}-ACME CORP-SALARY", 85000, 85000, 1),
    ("INT.PD:{ref}:SAVINGS INTEREST", 50, 600, 1),
    ("UPI/{ref}/REFUND MEGASTORE/{handle}@okexample", 200, 3000, 1),
    ("IMPS-{ref}-JOHN Q PUBLIC-SPLIT", 300, 2500, 1),
]


@dataclass
class Layout:
    name: str
    fmt: str  # csv | xlsx
    columns: list[str]  # logical keys, in file order
    headers: dict[str, str]
    date_fmt: str
    currency: str
    amount_mode: str  # signed | debit_credit | amount_with_type
    decimal: str = "."
    thousands: str = ","
    grouping: str = "western"  # western | indian
    decimals: int = 2
    sign_convention: str = "negative_is_debit"
    negative_style: str = "minus"  # minus | parens | trailing | drcr
    balance_drcr: bool = False
    delimiter: str = ","
    preamble: list[list[str]] = field(default_factory=list)
    reverse: bool = False
    multiline: bool = False
    opening_row: bool = False
    closing_row: bool = False
    totals_row: bool = False
    xlsx_native: bool = False
    duplicates: bool = True
    n: int = 45
    seed: int = 0
    start: date = date(2024, 1, 3)

    @property
    def extension(self) -> str:
        if self.fmt == "xlsx":
            return "xlsx"
        return "tsv" if self.delimiter == "\t" else "csv"


PREAMBLE = [
    ["Example Bank Ltd - Account Statement"],
    ["Account Holder:", "JANE DOE"],
    ["Account No:", "XXXXXXXX1234"],
    ["Statement Period:", "01/01/2024 to 31/03/2024"],
    [],
]

LAYOUTS: list[Layout] = [
    Layout(
        name="in_debit_credit_ddmmyy",
        fmt="csv",
        columns=["date", "desc", "ref", "value_date", "debit", "credit", "balance"],
        headers={"date": "Date", "desc": "Narration", "ref": "Chq./Ref.No.",
                 "value_date": "Value Dt", "debit": "Withdrawal Amt.",
                 "credit": "Deposit Amt.", "balance": "Closing Balance"},
        date_fmt="%d/%m/%y", currency="INR", amount_mode="debit_credit",
        grouping="indian", preamble=PREAMBLE, totals_row=True, seed=1,
    ),
    Layout(
        name="us_signed_mmddyyyy",
        fmt="csv",
        columns=["date", "desc", "amount", "balance"],
        headers={"date": "Posting Date", "desc": "Description", "amount": "Amount",
                 "balance": "Running Bal."},
        date_fmt="%m/%d/%Y", currency="USD", amount_mode="signed", seed=2,
    ),
    Layout(
        name="de_semicolon_eu_numbers",
        fmt="csv",
        columns=["date", "value_date", "desc", "amount", "balance"],
        headers={"date": "Buchungstag", "value_date": "Valuta", "desc": "Verwendungszweck",
                 "amount": "Betrag", "balance": "Saldo"},
        date_fmt="%d.%m.%Y", currency="EUR", amount_mode="signed",
        decimal=",", thousands=".", delimiter=";", seed=3,
    ),
    Layout(
        name="iso_shuffled_debit_credit",
        fmt="csv",
        columns=["balance", "credit", "debit", "desc", "date"],
        headers={"balance": "Balance", "credit": "Credit", "debit": "Debit",
                 "desc": "Transaction Details", "date": "Date"},
        date_fmt="%Y-%m-%d", currency="SGD", amount_mode="debit_credit", seed=4,
    ),
    Layout(
        name="drcr_suffix_amounts",
        fmt="csv",
        columns=["date", "desc", "amount", "balance"],
        headers={"date": "Txn Date", "desc": "Particulars", "amount": "Amount",
                 "balance": "Balance"},
        date_fmt="%d-%m-%Y", currency="INR", amount_mode="signed", grouping="indian",
        negative_style="drcr", balance_drcr=True, seed=5,
    ),
    Layout(
        name="type_column_gbp",
        fmt="csv",
        columns=["date", "desc", "type", "amount", "balance"],
        headers={"date": "Date", "desc": "Details", "type": "Type", "amount": "Amount",
                 "balance": "Balance"},
        date_fmt="%d %b %Y", currency="GBP", amount_mode="amount_with_type", seed=6,
    ),
    Layout(
        name="reverse_chronological",
        fmt="csv",
        columns=["date", "desc", "amount", "balance"],
        headers={"date": "Date", "desc": "Memo", "amount": "Amount", "balance": "Balance"},
        date_fmt="%Y/%m/%d", currency="USD", amount_mode="signed", reverse=True, seed=7,
    ),
    Layout(
        name="no_balance_cad",
        fmt="csv",
        columns=["date", "desc", "debit", "credit"],
        headers={"date": "Transaction Date", "desc": "Description", "debit": "Withdrawals",
                 "credit": "Deposits"},
        date_fmt="%m-%d-%Y", currency="CAD", amount_mode="debit_credit", seed=8,
    ),
    Layout(
        name="xlsx_native_cells",
        fmt="xlsx",
        columns=["date", "desc", "ref", "debit", "credit", "balance"],
        headers={"date": "Txn Date", "desc": "Description", "ref": "Ref No",
                 "debit": "Debit", "credit": "Credit", "balance": "Balance"},
        date_fmt="%Y-%m-%d", currency="INR", amount_mode="debit_credit",
        thousands="", xlsx_native=True, preamble=PREAMBLE, seed=9,
    ),
    Layout(
        name="xlsx_eu_strings",
        fmt="xlsx",
        columns=["date", "desc", "amount", "balance"],
        headers={"date": "Datum", "desc": "Omschrijving", "amount": "Bedrag",
                 "balance": "Saldo"},
        date_fmt="%d/%m/%Y", currency="EUR", amount_mode="signed",
        decimal=",", thousands=".", seed=10,
    ),
    Layout(
        name="tsv_credit_card_positive_debits",
        fmt="csv",
        columns=["date", "value_date", "desc", "amount", "currency"],
        headers={"date": "Posting Date", "value_date": "Transaction Date",
                 "desc": "Description", "amount": "Amount", "currency": "Currency"},
        date_fmt="%d-%b-%y", currency="AUD", amount_mode="signed",
        sign_convention="positive_is_debit", delimiter="\t", seed=11,
    ),
    Layout(
        name="multiline_narration",
        fmt="csv",
        columns=["date", "desc", "debit", "credit", "balance"],
        headers={"date": "Date", "desc": "Particulars", "debit": "Debit", "credit": "Credit",
                 "balance": "Balance"},
        date_fmt="%d/%m/%Y", currency="INR", amount_mode="debit_credit", grouping="indian",
        multiline=True, seed=12,
    ),
    Layout(
        name="opening_closing_rows_space_thousands",
        fmt="csv",
        columns=["date", "desc", "ref", "amount", "balance"],
        headers={"date": "Value Date", "desc": "Narrative", "ref": "Reference",
                 "amount": "Amount", "balance": "Ledger Balance"},
        date_fmt="%d/%m/%Y", currency="ZAR", amount_mode="signed", thousands=" ",
        opening_row=True, closing_row=True, seed=13,
    ),
    Layout(
        name="chf_parentheses_apostrophe",
        fmt="csv",
        columns=["date", "desc", "amount", "balance"],
        headers={"date": "Date", "desc": "Booking text", "amount": "Amount (CHF)",
                 "balance": "Balance (CHF)"},
        date_fmt="%d.%m.%Y", currency="CHF", amount_mode="signed", thousands="'",
        negative_style="parens", seed=14,
    ),
    Layout(
        name="jpy_trailing_minus_no_decimals",
        fmt="csv",
        columns=["date", "desc", "amount", "balance"],
        headers={"date": "TRAN DATE", "desc": "DESCRIPTION", "amount": "AMOUNT",
                 "balance": "BALANCE"},
        date_fmt="%d%b%Y", currency="JPY", amount_mode="signed", decimals=0,
        negative_style="trailing", seed=15,
    ),
]  # fmt: skip


# --------------------------------------------------------------------------- data


@dataclass
class Txn:
    date: date
    amount: Decimal
    narration: str
    balance: Decimal = Decimal(0)


def _q(value: Decimal, decimals: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def make_transactions(layout: Layout) -> tuple[Decimal, list[Txn]]:
    rng = random.Random(layout.seed)
    scale = 100 if layout.currency == "JPY" else 1
    opening = _q(Decimal(rng.randint(20000, 150000)) * scale, layout.decimals)
    txns: list[Txn] = []
    day = layout.start
    for _ in range(layout.n):
        day += timedelta(days=rng.choice([0, 0, 1, 1, 2, 3]))
        template, lo, hi, direction = rng.choice(MERCHANTS)
        narration = template.format(
            ref=str(rng.randint(10**9, 10**10 - 1)),
            card="XXXX" + str(rng.randint(1000, 9999)),
            handle=rng.choice(["jdoe", "store77", "pay.merchant"]),
        )
        cents = Decimal(rng.randint(0, 99)) / 100 if lo != hi else Decimal(0)
        raw = (Decimal(rng.randint(lo, hi)) + cents) * scale
        txns.append(Txn(day, _q(raw, layout.decimals) * direction, narration))
    if layout.duplicates:
        # Two genuinely identical transactions on the same day (must both be kept).
        dup = Txn(txns[10].date, Decimal("-250.00") * scale, "UPI/7777777777/CHAI POINT/jdoe@ybl")
        dup.amount = _q(dup.amount, layout.decimals)
        txns.insert(11, Txn(dup.date, dup.amount, dup.narration))
        txns.insert(11, Txn(dup.date, dup.amount, dup.narration))
    running = opening
    for t in txns:
        running += t.amount
        t.balance = running
    return opening, txns


# ----------------------------------------------------------------------- formatting


def group_digits(int_part: str, sep: str, style: str) -> str:
    if not sep or len(int_part) <= 3:
        return int_part
    if style == "indian":
        head, tail = int_part[:-3], int_part[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        return sep.join([*groups, tail])
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    return sep.join(groups)


def fmt_number(value: Decimal, layout: Layout) -> str:
    """Format an absolute value with the layout's separators."""
    text = f"{abs(value):.{layout.decimals}f}"
    int_part, _, frac = text.partition(".")
    out = group_digits(int_part, layout.thousands, layout.grouping)
    return f"{out}{layout.decimal}{frac}" if frac else out


def fmt_signed(value: Decimal, layout: Layout) -> str:
    """Format a signed amount using the layout's sign convention and negative style."""
    if layout.sign_convention == "positive_is_debit":
        value = -value
    body = fmt_number(value, layout)
    if layout.negative_style == "drcr":
        return f"{body} {'Dr' if value < 0 else 'Cr'}"
    if value >= 0:
        return body
    if layout.negative_style == "parens":
        return f"({body})"
    if layout.negative_style == "trailing":
        return f"{body}-"
    return f"-{body}"


def fmt_balance(value: Decimal, layout: Layout) -> str:
    if layout.balance_drcr:
        return f"{fmt_number(value, layout)} {'Dr' if value < 0 else 'Cr'}"
    return (
        fmt_signed(value, layout) if layout.negative_style != "drcr" else fmt_number(value, layout)
    )


def row_cells(t: Txn, layout: Layout) -> dict[str, Any]:
    native = layout.xlsx_native
    cells: dict[str, Any] = {
        "date": t.date if native else t.date.strftime(layout.date_fmt),
        "value_date": t.date if native else t.date.strftime(layout.date_fmt),
        "desc": t.narration,
        "ref": "" if native else f"REF{zlib.crc32(f'{t.narration}{t.date}'.encode()) % 10**8:08d}",
        "currency": layout.currency,
        "debit": "",
        "credit": "",
        "amount": "",
        "type": "",
        "balance": float(t.balance) if native else fmt_balance(t.balance, layout),
    }
    if layout.amount_mode == "debit_credit":
        key = "debit" if t.amount < 0 else "credit"
        cells[key] = float(abs(t.amount)) if native else fmt_number(t.amount, layout)
    elif layout.amount_mode == "amount_with_type":
        cells["amount"] = fmt_number(t.amount, layout)
        cells["type"] = "DR" if t.amount < 0 else "CR"
    else:
        cells["amount"] = fmt_signed(t.amount, layout)
    return cells


def build_rows(
    layout: Layout, opening: Decimal, txns: list[Txn]
) -> tuple[list[list[Any]], list[str]]:
    header = [layout.headers[c] for c in layout.columns]
    blank = dict.fromkeys(layout.columns, "")
    rows: list[list[Any]] = [list(r) for r in layout.preamble]
    rows.append(header)
    if layout.opening_row:
        cells = {**blank, "desc": "Opening Balance", "balance": fmt_balance(opening, layout)}
        rows.append([cells[c] for c in layout.columns])

    ordered = list(reversed(txns)) if layout.reverse else txns
    for i, t in enumerate(ordered):
        cells = row_cells(t, layout)
        continuation = None
        if layout.multiline and i % 4 == 0 and " " in t.narration:
            first, rest = t.narration.split(" ", 1)
            cells["desc"] = first
            continuation = rest
        rows.append([cells.get(c, "") for c in layout.columns])
        if continuation:
            rows.append([continuation if c == "desc" else "" for c in layout.columns])

    if layout.totals_row:
        debits = -sum((t.amount for t in txns if t.amount < 0), Decimal(0))
        credits = sum((t.amount for t in txns if t.amount > 0), Decimal(0))
        cells = {**blank, "desc": "Total", "debit": fmt_number(debits, layout),
                 "credit": fmt_number(credits, layout)}  # fmt: skip
        rows.append([cells[c] for c in layout.columns])
    if layout.closing_row:
        cells = {
            **blank,
            "desc": "Closing Balance",
            "balance": fmt_balance(txns[-1].balance, layout),
        }
        rows.append([cells[c] for c in layout.columns])
    return rows, header


# --------------------------------------------------------------------------- output


def mapping_for(layout: Layout) -> dict[str, Any]:
    idx = {c: i for i, c in enumerate(layout.columns)}
    return {
        "date_column": idx["date"],
        "description_columns": [idx["desc"]],
        "amount_mode": layout.amount_mode,
        "amount_column": idx.get("amount"),
        "debit_column": idx.get("debit"),
        "credit_column": idx.get("credit"),
        "type_column": idx.get("type"),
        "balance_column": idx.get("balance"),
        "date_format": layout.date_fmt,
        "decimal_separator": layout.decimal,
        "thousands_separator": layout.thousands,
        "currency": layout.currency,
        "sign_convention": layout.sign_convention,
        "drcr_markers": layout.negative_style == "drcr" or layout.balance_drcr,
    }


def write_csv(path: Path, rows: list[list[Any]], delimiter: str) -> None:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerows(rows)
    # Bytes, not text mode: Windows would otherwise turn every LF into CRLF.
    path.write_bytes(buf.getvalue().encode("utf-8"))


def write_xlsx(path: Path, rows: list[list[Any]]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    for row in rows:
        ws.append([None if v == "" else v for v in row])
    for cell in ws["A"]:
        if isinstance(cell.value, date):
            cell.number_format = "DD-MM-YYYY"
    wb.save(path)


def generate(layout: Layout, out_dir: Path = OUT_DIR) -> Path:
    opening, txns = make_transactions(layout)
    rows, header = build_rows(layout, opening, txns)
    out_dir.mkdir(parents=True, exist_ok=True)
    data_path = out_dir / f"{layout.name}.{layout.extension}"
    if layout.fmt == "xlsx":
        write_xlsx(data_path, rows)
    else:
        write_csv(data_path, rows, layout.delimiter)

    has_balance = "balance" in layout.columns
    truth = {
        "layout": layout.name,
        "file": data_path.name,
        "header": header,
        "mapping": mapping_for(layout),
        "expected": {
            "count": len(txns),
            "opening_balance": str(opening) if has_balance else None,
            "closing_balance": str(txns[-1].balance) if has_balance else None,
            "transactions": [
                {
                    "date": t.date.isoformat(),
                    "amount": str(t.amount),
                    "balance": str(t.balance) if has_balance else None,
                    "narration": t.narration,
                }
                for t in txns
            ],
        },
    }
    text = json.dumps(truth, indent=1, ensure_ascii=False) + "\n"
    (out_dir / f"{layout.name}.truth.json").write_bytes(text.encode("utf-8"))
    return data_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--list", action="store_true", help="list layouts and exit")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output directory")
    args = parser.parse_args()
    if args.list:
        for layout in LAYOUTS:
            print(f"{layout.name:40s} {layout.extension:5s} {layout.currency} {layout.amount_mode}")
        return
    for layout in LAYOUTS:
        path = generate(layout, args.out)
        print(f"wrote {path.relative_to(args.out.parent) if args.out == OUT_DIR else path}")


if __name__ == "__main__":
    main()
