from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.normalize import (
    AmountParseError,
    parse_amount,
    parse_date,
    suggest_date_formats,
)


@pytest.mark.parametrize(
    ("raw", "dec", "thou", "value", "marker"),
    [
        ("1,234.56", ".", ",", "1234.56", None),
        ("-1,234.56", ".", ",", "-1234.56", None),
        ("1.234,56", ",", ".", "1234.56", None),
        ("-1.234,56", ",", ".", "-1234.56", None),
        ("1,23,456.78", ".", ",", "123456.78", None),  # Indian grouping
        ("1'234.50", ".", "'", "1234.50", None),
        ("12 345.00", ".", " ", "12345.00", None),
        ("(1,234.56)", ".", ",", "-1234.56", None),
        ("1,234.56-", ".", ",", "-1234.56", None),
        ("1,234-", ".", ",", "-1234", None),
        ("+50.00", ".", ",", "50.00", None),
        ("1,200.00 Dr", ".", ",", "1200.00", "dr"),
        ("1,200.00Cr", ".", ",", "1200.00", "cr"),
        ("1,200.00 (Cr)", ".", ",", "1200.00", "cr"),
        ("Dr 1,200.00", ".", ",", "1200.00", "dr"),
        ("$1,234.56", ".", ",", "1234.56", None),
        ("€ 1.234,56", ",", ".", "1234.56", None),
        ("INR 500.00", ".", ",", "500.00", None),
        ("₹2,500", ".", ",", "2500", None),
        ("1234.5", ".", "", "1234.5", None),
        (".50", ".", ",", "0.50", None),
    ],
)
def test_parse_amount(raw: str, dec: str, thou: str, value: str, marker: str | None) -> None:
    parsed = parse_amount(raw, dec, thou)
    assert parsed is not None
    assert parsed.value == Decimal(value)
    assert parsed.marker == marker


@pytest.mark.parametrize("raw", ["", "  ", "-", "--", "—", "nil"])
def test_parse_amount_empty(raw: str) -> None:
    assert parse_amount(raw, ".", ",") is None


@pytest.mark.parametrize("raw", ["abc", "12.34.56", "1,2a", "Dr"])
def test_parse_amount_rejects_garbage(raw: str) -> None:
    with pytest.raises(AmountParseError):
        parse_amount(raw, ".", ",")


@pytest.mark.parametrize(
    ("raw", "fmt", "expected"),
    [
        ("05/01/2024", "%d/%m/%Y", date(2024, 1, 5)),
        ("01/05/2024", "%m/%d/%Y", date(2024, 1, 5)),
        ("2024-01-05", "%Y-%m-%d", date(2024, 1, 5)),
        ("2024-01-05 00:00:00", "%Y-%m-%d", date(2024, 1, 5)),
        ("05-JAN-24", "%d-%b-%y", date(2024, 1, 5)),
        ("05 Jan  2024", "%d %b %Y", date(2024, 1, 5)),
        ("05JAN2024", "%d%b%Y", date(2024, 1, 5)),
    ],
)
def test_parse_date(raw: str, fmt: str, expected: date) -> None:
    assert parse_date(raw, fmt) == expected


def test_parse_date_rejects_mismatch() -> None:
    with pytest.raises(ValueError):
        parse_date("13/25/2024", "%d/%m/%Y")


def test_suggest_date_formats_disambiguates_day_first() -> None:
    suggestions = suggest_date_formats(["05/01/2024", "25/01/2024"])
    assert "%d/%m/%Y" in suggestions
    assert "%m/%d/%Y" not in suggestions
