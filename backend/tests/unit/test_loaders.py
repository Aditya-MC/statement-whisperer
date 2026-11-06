from __future__ import annotations

import io
from datetime import date

import pytest
from openpyxl import Workbook

from app.ingestion.detect import FileType, UnsupportedFileError, detect_file_type, ensure_supported
from app.ingestion.loaders import FileReadError, load_raw_table, sniff_delimiter, split_header


def _xlsx(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_detect_types() -> None:
    assert detect_file_type("a.csv", b"Date,Amount\n") == FileType.csv
    assert detect_file_type("a.pdf", b"%PDF-1.7 ...") == FileType.pdf
    assert detect_file_type("a.png", b"\x89PNG\r\n\x1a\n") == FileType.image
    assert detect_file_type("a.xlsx", _xlsx([["a"]])) == FileType.xlsx
    assert detect_file_type("a.bin", b"\x00\x01\x02") == FileType.unknown


def test_unsupported_types_raise_with_hint() -> None:
    with pytest.raises(UnsupportedFileError, match="PDF"):
        ensure_supported(FileType.pdf)


@pytest.mark.parametrize("delim", [",", ";", "\t", "|"])
def test_sniff_delimiter_ignores_preamble(delim: str) -> None:
    text = "My Bank, Statement\nName: JANE\n" + "\n".join(
        delim.join(["05/01/2024", "Coffee, large", "-3.50", "100.00"]).replace(
            "Coffee, large", '"Coffee, large"' if delim == "," else "Coffee, large"
        )
        for _ in range(10)
    )
    assert sniff_delimiter(text) == delim


def test_csv_header_detection_skips_preamble() -> None:
    data = (
        b"Example Bank\nAccount No:,XXXX1234\nStatement Date:,31/01/2024\n\n"
        b"Date,Description,Amount,Balance\n05/01/2024,Coffee,-3.50,96.50\n"
    )
    table = split_header(load_raw_table(data, FileType.csv))
    assert table.header == ["Date", "Description", "Amount", "Balance"]
    assert table.body[0][1] == "Coffee"
    assert table.first_row_number == 6


def test_headerless_csv() -> None:
    data = b"05/01/2024,Coffee,-3.50,96.50\n06/01/2024,Tea,-2.00,94.50\n"
    table = split_header(load_raw_table(data, FileType.csv))
    assert not table.has_header
    assert table.header == ["Column 1", "Column 2", "Column 3", "Column 4"]
    assert len(table.body) == 2


def test_cp1252_csv_decodes() -> None:
    data = "Date,Description,Amount\n05/01/2024,Café,-3.50\n".encode("cp1252")
    table = split_header(load_raw_table(data, FileType.csv))
    assert table.body[0][1] == "Café"


def test_xlsx_native_cells_are_canonicalized() -> None:
    data = _xlsx([["Date", "Description", "Debit", "Balance"],
                  [date(2024, 1, 5), "Coffee", 3.5, 1234.56]])  # fmt: skip
    table = split_header(load_raw_table(data, FileType.xlsx))
    assert table.body[0] == ["2024-01-05", "Coffee", "3.5", "1234.56"]


def test_no_header_found() -> None:
    with pytest.raises(FileReadError):
        split_header(load_raw_table(b"just,some\ntext,here\n", FileType.csv))
