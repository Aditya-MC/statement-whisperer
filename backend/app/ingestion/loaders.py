"""Load a statement file into a raw grid of strings and locate the header row.

Every loader returns a `RawTable`: a list of rows, each a list of cell strings, padded to equal
width. Values are not interpreted here, apart from XLSX native cells (dates and numbers), which
are turned into canonical strings so the rest of the pipeline treats CSV and XLSX the same way.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

import pandas as pd

from app.ingestion.detect import FileType, UnsupportedFileError
from app.services.masking import is_amount_like, is_date_like

RawTable = list[list[str]]

_DELIMITERS = [",", ";", "\t", "|"]
_ENCODINGS = ["utf-8-sig", "cp1252", "latin-1"]
_MAX_HEADER_SCAN = 60


class FileReadError(ValueError):
    """The file could not be read. The message never contains file contents."""


@dataclass
class Table:
    """A loaded table split into header and body. `first_row_number` is the 1-based file row
    number of `body[0]`, which is used in validation messages."""

    header: list[str]
    body: RawTable
    first_row_number: int
    has_header: bool


def load_raw_table(data: bytes, file_type: FileType) -> RawTable:
    if file_type == FileType.csv:
        return _load_csv(data)
    if file_type == FileType.xlsx:
        return _load_xlsx(data)
    raise UnsupportedFileError(f"No loader for {file_type}")


# --------------------------------------------------------------------------- CSV


def _decode(data: bytes) -> str:
    for enc in _ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise FileReadError("Could not decode the file as text")


def sniff_delimiter(text: str) -> str:
    """Pick the delimiter whose most common field count (>1) covers the most cells.

    Score = (lines sharing the modal width) x (modal width - 1). This prefers the delimiter
    that splits many lines into many columns, so a stray comma inside narrations of a
    semicolon file (2 fields per line) loses to the real delimiter (5 fields per line).
    `csv.Sniffer` is unreliable when a statement starts with free-text preamble lines.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()][:200]
    best, best_score = ",", -1
    for delim in _DELIMITERS:
        counts = [len(row) for row in csv.reader(lines, delimiter=delim)]
        width_freq = Counter(c for c in counts if c > 1)
        if not width_freq:
            continue
        width, freq = width_freq.most_common(1)[0]
        score = freq * (width - 1)
        if score > best_score:
            best, best_score = delim, score
    return best


def _load_csv(data: bytes) -> RawTable:
    text = _decode(data)
    delim = sniff_delimiter(text)
    try:
        rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delim)]
    except csv.Error as exc:
        raise FileReadError("Malformed CSV") from exc
    return _pad(rows)


# -------------------------------------------------------------------------- XLSX


def _cell_to_str(value: Any) -> str:
    """Canonical string for a spreadsheet cell. Dates become ISO strings and numbers plain
    decimals, so the inferred mapping for XLSX files is predictable (%Y-%m-%d, '.' decimal)."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d") if value.time() == time(0) else value.isoformat(" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.10f}".rstrip("0").rstrip(".")
    return str(value).strip()


def _load_xlsx(data: bytes) -> RawTable:
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=object)
    except Exception as exc:  # openpyxl raises many types; never echo their messages
        raise FileReadError("Could not read the spreadsheet") from exc
    if not sheets:
        raise FileReadError("The spreadsheet has no sheets")
    # Statements usually live on the first sheet; choose the largest non-empty one to be safe.
    frame = max(sheets.values(), key=lambda df: int(df.notna().sum().sum()))
    rows = [[_cell_to_str(v) for v in row] for row in frame.itertuples(index=False, name=None)]
    return _pad(rows)


# ------------------------------------------------------------------------ helpers


def _pad(rows: RawTable) -> RawTable:
    width = max((len(r) for r in rows), default=0)
    padded = [r + [""] * (width - len(r)) for r in rows]
    # Drop columns that are empty in every row (common at the right edge of exports).
    keep = [i for i in range(width) if any(r[i] for r in padded)]
    return [[r[i] for i in keep] for r in padded]


#: A transaction table needs at least date, description and amount.
_MIN_TABLE_CELLS = 3


def _is_header_like(row: list[str]) -> bool:
    cells = [c for c in row if c]
    if len(cells) < _MIN_TABLE_CELLS:
        return False
    texty = sum(1 for c in cells if not is_date_like(c) and not is_amount_like(c))
    return texty >= int(len(cells) * 0.7)


def _has_date(row: list[str]) -> bool:
    """A data row: contains a date and enough populated cells to be a transaction."""
    return sum(1 for c in row if c) >= _MIN_TABLE_CELLS and any(is_date_like(c) for c in row)


def split_header(table: RawTable) -> Table:
    """Find the header row: the first text-heavy row followed (within a couple of rows) by a
    row containing a date. Rows above it are preamble (bank name, account holder, etc.)."""
    if not table:
        raise FileReadError("The file is empty")
    nonempty = [i for i, r in enumerate(table) if any(r)]
    if nonempty and _has_date(table[nonempty[0]]):
        width = len(table[0])
        return Table(
            header=[f"Column {i + 1}" for i in range(width)],
            body=table[nonempty[0] :],
            first_row_number=nonempty[0] + 1,
            has_header=False,
        )
    for pos, i in enumerate(nonempty[:_MAX_HEADER_SCAN]):
        if not _is_header_like(table[i]):
            continue
        following = nonempty[pos + 1 : pos + 4]
        if any(_has_date(table[j]) for j in following):
            return Table(
                header=table[i],
                body=table[i + 1 :],
                first_row_number=i + 2,
                has_header=True,
            )
    raise FileReadError(
        "Could not find a header row followed by dated transactions in the first "
        f"{_MAX_HEADER_SCAN} rows"
    )
