"""Dashboard analytics: definitions, grouping, time buckets, currencies, recurring payments."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.analytics import dashboard
from app.categorization.categorizer import load_category_index
from app.models import Account, Import, ImportStatus, Transaction, TxnType

_seq = count()


@pytest.fixture
def imp(db: Session, account: Account) -> Import:
    i = Import(account_id=account.id, file_hash="a" * 64, file_type="csv",
               status=ImportStatus.completed, parser_version="test")  # fmt: skip
    db.add(i)
    db.commit()
    return i


def add(
    db: Session,
    imp: Import,
    d: date,
    amount: str,
    *,
    category: str | None = None,
    merchant: str | None = None,
    currency: str = "USD",
    transfer: bool = False,
) -> Transaction:
    amt = Decimal(amount)
    cat_id = load_category_index(db).by_path[category] if category else None
    t = Transaction(
        account_id=imp.account_id, import_id=imp.id, date=d, amount=amt,
        type=TxnType.debit if amt < 0 else TxnType.credit, balance=None, currency=currency,
        raw_narration=merchant or "x", cleaned_merchant=merchant, row_index=next(_seq),
        dedupe_hash=f"a{next(_seq)}", category_id=cat_id, is_transfer=transfer,
    )  # fmt: skip
    db.add(t)
    db.flush()
    return t


D = date(2026, 10, 1)


def test_summary_definitions(db: Session, imp: Import) -> None:
    add(db, imp, D, "1000.00", category="Income > Salary", merchant="ACME")
    add(db, imp, D, "-200.00", category="Food > Groceries", merchant="MART")
    add(db, imp, D, "-50.00", category="Food > Restaurants", merchant="CAFE")
    add(db, imp, D, "20.00", category="Income > Refunds", merchant="MART")
    add(db, imp, D, "-300.00", category="Transfers > Self Transfer", transfer=True)
    add(db, imp, D, "-40.00", category="Transfers > Transfer to Others", merchant="JOHN Q")

    s = dashboard(db)["summary"]
    assert s["income"] == "1000.00"
    assert s["refunds"] == "20.00"
    assert s["money_out"] == "290.00"  # own transfer excluded; paying a person counts
    assert s["spending"] == "270.00"  # refunds undo spending
    assert s["net"] == "730.00"
    assert s["savings_rate"] == pytest.approx(0.73)
    assert s["excluded_transfers"] == 1


def test_self_transfer_category_excluded_even_if_not_linked(db: Session, imp: Import) -> None:
    add(db, imp, D, "-500.00", category="Transfers > Self Transfer")
    assert dashboard(db)["summary"]["money_out"] == "0.00"


def test_no_income_means_no_savings_rate(db: Session, imp: Import) -> None:
    add(db, imp, D, "-10.00")
    assert dashboard(db)["summary"]["savings_rate"] is None


def test_by_category_groups_parents_and_uncategorized(db: Session, imp: Import) -> None:
    add(db, imp, D, "-200.00", category="Food > Groceries")
    add(db, imp, D, "-50.00", category="Food > Restaurants")
    add(db, imp, D, "-30.00")
    rows = dashboard(db)["by_category"]
    assert [(r["name"], r["amount"], r["count"]) for r in rows] == [
        ("Food", "250.00", 2),
        ("Uncategorized", "30.00", 1),
    ]
    food_group = (
        load_category_index(db).by_id[load_category_index(db).by_path["Food > Groceries"]].parent_id
    )
    assert rows[0]["category_id"] == food_group
    assert rows[0]["share"] == pytest.approx(250 / 280)


def test_more_than_eight_groups_fold_into_other(db: Session, imp: Import) -> None:
    paths = ["Food > Groceries", "Housing > Rent", "Transport > Fuel", "Shopping > Clothing",
             "Bills > Subscriptions", "Health > Medical", "Leisure > Travel", "Education > Tuition",
             "Cash > ATM Withdrawal", "Financial > Taxes"]  # fmt: skip
    for i, p in enumerate(paths):
        add(db, imp, D, f"-{100 - i}.00", category=p)
    rows = dashboard(db)["by_category"]
    assert len(rows) == 9
    assert rows[-1]["name"] == "Other (2)" and rows[-1]["is_other"] is True
    assert rows[-1]["amount"] == f"{91 + 92}.00"


def test_weekly_series_for_short_ranges_fills_gaps(db: Session, imp: Import) -> None:
    add(db, imp, date(2026, 10, 1), "-10.00")
    add(db, imp, date(2026, 10, 20), "-30.00")
    add(db, imp, date(2026, 10, 21), "5.00", category="Income > Refunds")
    out = dashboard(db, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
    assert out["period"]["granularity"] == "week"
    series = out["series"]
    assert series[0]["start"] == "2026-09-28"  # Monday of the first week
    assert [s["spending"] for s in series] == ["10.00", "0.00", "0.00", "25.00", "0.00"]


def test_monthly_series_for_long_ranges(db: Session, imp: Import) -> None:
    add(db, imp, date(2026, 1, 15), "100.00", category="Income > Salary")
    add(db, imp, date(2026, 3, 15), "-40.00")
    out = dashboard(db)
    assert out["period"]["granularity"] == "month"
    assert [(s["label"], s["income"], s["spending"]) for s in out["series"]] == [
        ("Jan 2026", "100.00", "0.00"),
        ("Feb 2026", "0.00", "0.00"),
        ("Mar 2026", "0.00", "40.00"),
    ]


def test_currencies_are_never_mixed(db: Session, imp: Import) -> None:
    add(db, imp, D, "-10.00", currency="INR")
    add(db, imp, D, "-20.00", currency="INR")
    add(db, imp, D, "-99.00", currency="USD")
    default = dashboard(db)
    assert default["currency"] == "INR" and default["currencies"] == ["INR", "USD"]
    assert default["summary"]["money_out"] == "30.00"
    assert dashboard(db, currency="usd")["summary"]["money_out"] == "99.00"


def test_top_merchants(db: Session, imp: Import) -> None:
    for _ in range(3):
        add(db, imp, D, "-10.00", merchant="SMALL")
    add(db, imp, D, "-50.00", merchant="BIG")
    tops = dashboard(db)["top_merchants"]
    assert [(t["merchant"], t["amount"], t["count"]) for t in tops] == [
        ("BIG", "50.00", 1),
        ("SMALL", "30.00", 3),
    ]


def monthly(
    db: Session, imp: Import, merchant: str, amounts: list[str], start: date, gap: int = 30
) -> None:
    for i, a in enumerate(amounts):
        add(db, imp, start + timedelta(days=gap * i), a, merchant=merchant)


def test_recurring_monthly_detected(db: Session, imp: Import) -> None:
    monthly(db, imp, "MYJIO", ["-349.00", "-349.00", "-349.00", "-399.00"], date(2026, 7, 5))
    rec = dashboard(db, date_to=date(2026, 10, 20))["recurring"]
    assert len(rec) == 1
    r = rec[0]
    assert r["merchant"] == "MYJIO" and r["cadence"] == "monthly" and r["occurrences"] == 4
    assert r["typical_amount"] == "349.00"
    assert r["next_expected"] == (date(2026, 7, 5) + timedelta(days=120)).isoformat()


def test_recurring_weekly_detected_with_monthly_cost(db: Session, imp: Import) -> None:
    monthly(db, imp, "MILK", ["-60.00"] * 5, date(2026, 9, 1), gap=7)
    r = dashboard(db, date_to=date(2026, 10, 1))["recurring"][0]
    assert r["cadence"] == "weekly"
    assert Decimal(r["monthly_cost"]) == Decimal("260.00")  # 60 * 52 / 12


@pytest.mark.parametrize(
    ("amounts", "gap", "as_of"),
    [
        (["-100.00", "-100.00"], 30, date(2026, 9, 1)),  # too few payments
        (["-100.00", "-100.00", "-100.00", "-100.00"], 12, date(2026, 9, 1)),  # not weekly/monthly
        (["-100.00", "-300.00", "-100.00", "-100.00"], 30, date(2026, 10, 1)),  # amount varies
        (["-100.00", "-100.00", "-100.00"], 30, date(2027, 3, 1)),  # stopped long ago
    ],
)
def test_recurring_rejects_irregular(
    db: Session, imp: Import, amounts: list[str], gap: int, as_of: date
) -> None:
    monthly(db, imp, "THING", amounts, date(2026, 6, 1), gap=gap)
    assert dashboard(db, date_to=as_of)["recurring"] == []


def test_recurring_looks_back_beyond_selected_range(db: Session, imp: Import) -> None:
    monthly(db, imp, "NETFLIX", ["-649.00"] * 4, date(2026, 7, 1))
    out = dashboard(db, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
    assert [r["merchant"] for r in out["recurring"]] == ["NETFLIX"]


def test_empty_database(db: Session) -> None:
    out = dashboard(db)
    assert out["currency"] is None and out["series"] == [] and out["by_category"] == []
    assert out["summary"]["spending"] == "0.00"


def test_api_endpoint(client: TestClient) -> None:
    r = client.get("/api/analytics/dashboard")
    assert r.status_code == 200 and r.json()["summary"]["transactions"] == 0
    bad = client.get(
        "/api/analytics/dashboard", params={"date_from": "2026-10-31", "date_to": "2026-10-01"}
    )
    assert bad.status_code == 422


def test_pie_top_groups_plus_other(db: Session, imp: Import) -> None:
    spend = {
        "Housing > Rent": 600,
        "Food > Groceries": 300,
        "Transport > Fuel": 200,
        "Bills > Subscriptions": 100,
        "Health > Medical": 50,
        "Leisure > Travel": 30,
    }
    for path, amount in spend.items():
        add(db, imp, D, f"-{amount}.00", category=path)
    add(db, imp, D, "-20.00")  # uncategorized
    pie = dashboard(db)["pie"]
    assert [(p["name"], p["slot"]) for p in pie] == [
        ("Housing", 0), ("Food", 1), ("Transport", 2), ("Bills", 3), ("Health", 4), ("Other", None)
    ]  # fmt: skip
    assert pie[-1]["amount"] == "50.00"  # Leisure + uncategorized
    assert sum(p["share"] for p in pie) == pytest.approx(1.0)


def test_pie_colors_follow_the_category_not_the_period(db: Session, imp: Import) -> None:
    """Slot = all-time rank, so narrowing the date range never repaints a slice."""
    add(db, imp, date(2026, 9, 1), "-1000.00", category="Housing > Rent")
    add(db, imp, date(2026, 10, 1), "-100.00", category="Food > Groceries")
    add(db, imp, date(2026, 10, 2), "-50.00", category="Transport > Fuel")
    october = dashboard(db, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))["pie"]
    # Food is #1 in October but keeps its all-time slot (Housing holds slot 0).
    assert [(p["name"], p["slot"]) for p in october] == [("Food", 1), ("Transport", 2)]


def test_pie_empty_without_spending(db: Session, imp: Import) -> None:
    add(db, imp, D, "100.00", category="Income > Salary")
    assert dashboard(db)["pie"] == []
