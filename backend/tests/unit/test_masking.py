from __future__ import annotations

import pytest

from app.services.masking import build_masked_sample, mask_cell, mask_free_text


@pytest.mark.parametrize(
    "value",
    ["05/01/2024", "2024-01-05", "05 Jan 2024", "1,234.56", "-50.00", "1.234,56",
     "(1,234.56)", "1,200.00 Dr", "DR", "Credit", "INR", "123456"],
)  # fmt: skip
def test_mask_cell_keeps_format_signals(value: str) -> None:
    assert mask_cell(value) == value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("123456789012", "<digits:12>"),  # account / reference number
        ("4111111111111111", "<digits:16>"),  # card number
        ("UPI/123456/SWIGGY/jdoe@okaxis", "<text:29>"),
        ("JANE DOE", "<text:8>"),
        ("Rent for flat 4B", "<text:16>"),
    ],
)
def test_mask_cell_hides_identifiers_and_text(value: str, expected: str) -> None:
    assert mask_cell(value) == expected


def test_mask_free_text_keeps_merchant_words() -> None:
    masked = mask_free_text("UPI/412345678901/SWIGGY/jdoe@okaxis card XXXX1234 jane@mail.com")
    assert "SWIGGY" in masked
    for secret in ("412345678901", "jdoe@okaxis", "XXXX1234", "1234", "jane@mail.com"):
        assert secret not in masked


def test_build_masked_sample_limits_rows_and_masks() -> None:
    header = ["Date", "Narration", "Amount", "Acct 123456789"]
    rows = [["05/01/2024", f"PAYMENT TO JANE DOE {i}", "-10.00", "987654321"] for i in range(30)]
    sample = build_masked_sample(header, rows, max_rows=10)
    assert len(sample.rows) == 10
    assert sample.header[3] == "Acct <num>"
    flat = " ".join(" ".join(r) for r in sample.rows)
    assert "JANE" not in flat
    assert "987654321" not in flat
    assert "05/01/2024" in flat and "-10.00" in flat
