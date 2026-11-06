from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.loaders import Table
from app.ingestion.normalize import MappingError, normalize
from app.ingestion.validate import validate
from app.schemas.mapping import ColumnMapping

SIGNED = ColumnMapping(
    date_column=0, description_columns=[1], amount_mode="signed", amount_column=2,
    balance_column=3, date_format="%Y-%m-%d", currency="USD",
)  # fmt: skip
DC = ColumnMapping(
    date_column=0, description_columns=[1], amount_mode="debit_credit", debit_column=2,
    credit_column=3, balance_column=4, date_format="%Y-%m-%d", currency="USD",
)  # fmt: skip


def table(header: list[str], rows: list[list[str]]) -> Table:
    return Table(header=header, body=rows, first_row_number=2, has_header=True)


H4 = ["Date", "Desc", "Amount", "Balance"]
H5 = ["Date", "Desc", "Debit", "Credit", "Balance"]


def test_signed_statement_validates() -> None:
    t = table(H4, [
        ["2024-01-01", "Salary", "1000.00", "1100.00"],
        ["2024-01-02", "Coffee", "-3.50", "1096.50"],
        ["2024-01-02", "Coffee", "-3.50", "1093.00"],
    ])  # fmt: skip
    report = validate(normalize(t, SIGNED))
    assert report.ok, report.errors
    s = report.stats
    assert s.transactions == 3
    assert s.opening_balance == Decimal("100.00")
    assert s.closing_balance == Decimal("1093.00")
    assert s.total_credits == Decimal("1000.00") and s.total_debits == Decimal("7.00")
    assert (s.date_from, s.date_to) == (date(2024, 1, 1), date(2024, 1, 2))


def test_balance_mismatch_is_reported_with_row_number() -> None:
    t = table(H4, [
        ["2024-01-01", "A", "-10.00", "90.00"],
        ["2024-01-02", "B", "-10.00", "75.00"],  # should be 80.00
        ["2024-01-03", "C", "-5.00", "70.00"],
    ])  # fmt: skip
    report = validate(normalize(t, SIGNED))
    assert not report.ok
    mismatches = [e for e in report.errors if e.code == "balance_mismatch"]
    assert [e.row for e in mismatches] == [3]


def test_reverse_order_detected_from_balances() -> None:
    t = table(H4, [
        ["2024-01-03", "C", "-5.00", "75.00"],
        ["2024-01-02", "B", "-10.00", "80.00"],
        ["2024-01-01", "A", "-10.00", "90.00"],
    ])  # fmt: skip
    report = validate(normalize(t, SIGNED))
    assert report.ok, report.errors
    assert report.stats.order == "reverse"
    assert report.stats.opening_balance == Decimal("100.00")
    assert report.stats.closing_balance == Decimal("75.00")


def test_day_end_balances_only() -> None:
    t = table(H4, [
        ["2024-01-01", "A", "-10.00", ""],
        ["2024-01-01", "B", "-10.00", "80.00"],
        ["2024-01-02", "C", "-5.00", "75.00"],
    ])  # fmt: skip
    report = validate(normalize(t, SIGNED))
    assert report.ok, report.errors
    assert report.stats.opening_balance == Decimal("100.00")


def test_continuation_summary_and_opening_rows() -> None:
    t = table(H5, [
        ["", "Opening Balance", "", "", "100.00"],
        ["2024-01-01", "NEFT CR SALARY", "", "1,000.00", "1,100.00"],
        ["", "ACME CORP JAN", "", "", ""],
        ["2024-01-02", "Coffee", "3.50", "", "1,096.50"],
        ["", "Total", "3.50", "1,000.00", ""],
        ["", "Closing Balance", "", "", "1,096.50"],
    ])  # fmt: skip
    res = normalize(t, DC)
    assert [x.raw_narration for x in res.transactions] == ["NEFT CR SALARY ACME CORP JAN", "Coffee"]
    assert res.continuation_rows == 1 and res.skipped_rows == 3
    assert res.stated_opening == Decimal("100.00")
    assert res.stated_closing == Decimal("1096.50")
    assert validate(res).ok


def test_stated_closing_mismatch_fails() -> None:
    t = table(H5, [
        ["2024-01-01", "A", "10.00", "", "90.00"],
        ["", "Closing Balance", "", "", "95.00"],
    ])  # fmt: skip
    report = validate(normalize(t, DC))
    assert not report.ok
    assert any(e.code == "stated_closing_mismatch" for e in report.errors)


def test_wrong_date_format_fails_with_suggestion() -> None:
    m = SIGNED.model_copy(update={"date_format": "%m/%d/%Y"})
    t = table(H4, [["25/01/2024", "A", "-1.00", "9.00"], ["26/01/2024", "B", "-1.00", "8.00"]])
    report = validate(normalize(t, m))
    assert not report.ok
    assert report.issue_counts["date_parse"] == 2
    assert "%d/%m/%Y" in report.suggestions["date_format"]
    assert all("25/01" not in e.message for e in report.errors)  # no raw values in messages


def test_amount_without_date_is_an_error_not_dropped() -> None:
    t = table(H4, [["2024-01-01", "A", "-1.00", "9.00"], ["", "B", "-1.00", "8.00"]])
    report = validate(normalize(t, SIGNED))
    assert not report.ok
    assert report.stats.error_rows == 1
    assert report.stats.rows_in_file == 2


def test_type_column_mode() -> None:
    m = ColumnMapping(
        date_column=0, description_columns=[1], amount_mode="amount_with_type", amount_column=3,
        type_column=2, balance_column=4, date_format="%Y-%m-%d", currency="GBP",
    )  # fmt: skip
    t = table(["Date", "Desc", "Type", "Amount", "Balance"], [
        ["2024-01-01", "A", "CR", "50.00", "150.00"],
        ["2024-01-02", "B", "DR", "20.00", "130.00"],
    ])  # fmt: skip
    res = normalize(t, m)
    assert [x.amount for x in res.transactions] == [Decimal("50.00"), Decimal("-20.00")]
    assert validate(res).ok


def test_no_balance_column_warns() -> None:
    m = SIGNED.model_copy(update={"balance_column": None})
    report = validate(normalize(table(H4, [["2024-01-01", "A", "-1.00", ""]]), m))
    assert report.ok
    assert any(w.code == "no_balance" for w in report.warnings)


def test_mapping_out_of_range() -> None:
    m = SIGNED.model_copy(update={"balance_column": 9})
    with pytest.raises(MappingError):
        normalize(table(H4, [["2024-01-01", "A", "-1.00", "1"]]), m)


def test_mapping_validation_requires_mode_columns() -> None:
    with pytest.raises(ValueError):
        ColumnMapping(
            date_column=0, description_columns=[1], amount_mode="debit_credit",
            debit_column=2, date_format="%Y-%m-%d", currency="USD",
        )  # fmt: skip
