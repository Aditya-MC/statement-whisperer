"""Dashboard analytics computed from stored transactions.

Definitions (also shown in the UI):

* Transfers between your own accounts (`is_transfer`, or categorized *Self Transfer*) are
  excluded everywhere: they are neither income nor spending.
* **Income** = money in, except refunds.
* **Spending** = money out minus refunds (a refund undoes spending rather than earning money).
* **Net** = income - spending, which equals money in - money out.
* **Savings rate** = net / income (undefined when there is no income).
* Payments to other people (*Transfer to Others*) are real money out and count as spending.

Amounts in different currencies are never added together. Each response covers one currency:
the requested one, or the most common one in the filtered data.

Aggregation is done in Python with Decimal (exact, and the same on SQLite and Postgres).
That is plenty fast for a personal ledger of tens of thousands of rows.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.categorization.categorizer import REFUNDS, SELF_TRANSFER, load_category_index
from app.models import Account, Category, Transaction

ZERO = Decimal("0")
#: Up to this many days the time series is weekly; beyond it, monthly.
WEEKLY_MAX_DAYS = 45
TOP_CATEGORIES = 8
TOP_MERCHANTS = 10
RECURRING_LOOKBACK_DAYS = 400


@dataclass(frozen=True)
class _Row:
    date: date
    amount: Decimal
    currency: str
    category_id: int | None
    merchant: str | None
    excluded: bool  # own-account transfer


@dataclass
class _Tally:
    amount: Decimal = ZERO
    count: int = 0
    category_id: int | None = None

    def add(self, amount: Decimal, category_id: int | None = None) -> None:
        self.amount += amount
        self.count += 1
        if category_id is not None:
            self.category_id = category_id  # most recent one wins


def _money(d: Decimal) -> str:
    return format(d.quantize(Decimal("0.01")), "f")


def _load_rows(
    db: Session,
    user_id: int,
    account_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> list[_Row]:
    """`user_id`'s transactions only (optionally one of their accounts and a date range)."""
    idx = load_category_index(db, user_id)
    self_transfer = idx.by_path.get(SELF_TRANSFER)
    stmt = select(
        Transaction.date,
        Transaction.amount,
        Transaction.currency,
        Transaction.category_id,
        Transaction.cleaned_merchant,
        Transaction.is_transfer,
    ).where(Transaction.account_id.in_(select(Account.id).where(Account.user_id == user_id)))
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    return [
        _Row(
            date=r.date,
            amount=Decimal(r.amount),
            currency=r.currency,
            category_id=r.category_id,
            merchant=r.cleaned_merchant,
            excluded=bool(r.is_transfer)
            or (self_transfer is not None and r.category_id == self_transfer),
        )
        for r in db.execute(stmt)
    ]


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _bucket(d: date, granularity: str) -> date:
    return _week_start(d) if granularity == "week" else d.replace(day=1)


def _bucket_label(start: date, granularity: str) -> str:
    return f"{start.day} {start:%b}" if granularity == "week" else f"{start:%b %Y}"


def _next_bucket(start: date, granularity: str) -> date:
    if granularity == "week":
        return start + timedelta(days=7)
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1)


def _detect_recurring(rows: list[_Row], as_of: date) -> list[dict[str, object]]:
    """Merchants paid at a regular weekly or monthly rhythm with similar amounts.

    Needs at least 3 payments. "Regular" means at least 70% of the gaps fall within
    +-35% of the median gap, and amounts stay within +-25% of their median.
    """
    by_merchant: dict[str, list[_Row]] = defaultdict(list)
    for r in rows:
        if r.amount < 0 and not r.excluded and r.merchant and r.merchant != "UNKNOWN":
            by_merchant[r.merchant].append(r)

    found: list[dict[str, object]] = []
    for merchant, items in by_merchant.items():
        if len(items) < 3:
            continue
        items.sort(key=lambda r: r.date)
        gaps = [(b.date - a.date).days for a, b in pairwise(items)]
        gaps = [g for g in gaps if g > 0] or [0]
        median_gap = statistics.median(gaps)
        if 25 <= median_gap <= 35:
            cadence = "monthly"
        elif 6 <= median_gap <= 8:
            cadence = "weekly"
        else:
            continue
        regular = sum(1 for g in gaps if abs(g - median_gap) <= 0.35 * median_gap)
        if regular / len(gaps) < 0.7:
            continue
        amounts = [-r.amount for r in items]
        median_amount = statistics.median(amounts)
        if median_amount <= 0 or any(
            abs(a - median_amount) > median_amount * Decimal("0.25") for a in amounts
        ):
            continue
        last = items[-1].date
        next_expected = last + timedelta(days=round(median_gap))
        # Stopped subscriptions aren't "recurring" any more.
        if (as_of - last).days > median_gap * 1.5:
            continue
        found.append(
            {
                "merchant": merchant,
                "cadence": cadence,
                "typical_amount": _money(median_amount),
                "occurrences": len(items),
                "last_date": last.isoformat(),
                "next_expected": next_expected.isoformat(),
                "category_id": items[-1].category_id,
                "monthly_cost": _money(
                    median_amount * (Decimal(52) / 12 if cadence == "weekly" else 1)
                ),
            }
        )
    found.sort(key=lambda f: Decimal(str(f["monthly_cost"])), reverse=True)
    return found


#: Part-to-whole charts stay readable up to ~6 parts: 5 colored groups + a gray "Other".
PIE_SLOTS = 5


def _pie(
    db: Session,
    user_id: int,
    counted: list[_Row],
    by_group: dict[int | None, _Tally],
    money_out: Decimal,
    currency: str | None,
    group_of: Callable[[int | None], Category | None],
) -> list[dict[str, object]]:
    """Spending share per category group for the pie chart.

    Colors must follow the category, not its rank in the current view: a group's color slot
    is its rank by *all-time* spending (all accounts, this currency). Changing the date or
    account filter therefore never repaints a slice. Groups outside the top slots, and
    uncategorized spending, fold into one gray "Other" slice.
    """
    if not money_out:
        return []
    all_time = _load_rows(db, user_id, None, None, None)
    totals: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for r in all_time:
        if r.currency == currency and r.amount < 0 and not r.excluded:
            g = group_of(r.category_id)
            if g is not None:
                totals[g.id] += -r.amount
    slot_of = {
        gid: i
        for i, (gid, _) in enumerate(sorted(totals.items(), key=lambda kv: -kv[1])[:PIE_SLOTS])
    }

    slices: list[dict[str, object]] = []
    other = _Tally()
    for gid, tally in sorted(by_group.items(), key=lambda kv: kv[1].amount, reverse=True):
        if gid is not None and gid in slot_of:
            group = group_of(gid)
            name = group.name if group is not None else str(gid)
            slices.append(
                {
                    "category_id": gid,
                    "name": name,
                    "amount": _money(tally.amount),
                    "share": float(tally.amount / money_out),
                    "slot": slot_of[gid],
                }
            )
        else:
            other.amount += tally.amount
            other.count += tally.count
    if other.amount:
        slices.append(
            {
                "category_id": None,
                "name": "Other",
                "amount": _money(other.amount),
                "share": float(other.amount / money_out),
                "slot": None,
            }
        )
    return slices


def dashboard(
    db: Session,
    *,
    user_id: int,
    account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> dict[str, object]:
    """Everything the dashboard shows for `user_id`'s data (never anyone else's)."""
    # Currencies come from all of the account's data (not just this range), so the picker stays
    # stable as dates change and an empty range still has a currency for recurring payments.
    cur_stmt = (
        select(Transaction.currency, func.count())
        .where(Transaction.account_id.in_(select(Account.id).where(Account.user_id == user_id)))
        .group_by(Transaction.currency)
    )
    if account_id is not None:
        cur_stmt = cur_stmt.where(Transaction.account_id == account_id)
    currencies = [c for c, _ in sorted(db.execute(cur_stmt).all(), key=lambda r: -r[1])]
    chosen = (currency or "").upper() or (currencies[0] if currencies else None)
    rows = [
        r for r in _load_rows(db, user_id, account_id, date_from, date_to) if r.currency == chosen
    ]

    idx = load_category_index(db, user_id)
    refunds_id = idx.by_path.get(REFUNDS)
    cats = idx.by_id

    def group_of(category_id: int | None) -> Category | None:
        c = cats.get(category_id) if category_id is not None else None
        if c is not None and c.parent_id is not None:
            return cats.get(c.parent_id)
        return c

    counted = [r for r in rows if not r.excluded]
    money_in = sum((r.amount for r in counted if r.amount > 0), ZERO)
    money_out = -sum((r.amount for r in counted if r.amount < 0), ZERO)
    refunds = sum((r.amount for r in counted if r.amount > 0 and r.category_id == refunds_id), ZERO)
    income = money_in - refunds
    spending = money_out - refunds
    net = income - spending
    savings_rate = float(net / income) if income > 0 else None

    # ---- period + time series
    start = date_from or (min(r.date for r in rows) if rows else None)
    end = date_to or (max(r.date for r in rows) if rows else None)
    series: list[dict[str, object]] = []
    granularity = "month"
    if start and end:
        granularity = "week" if (end - start).days <= WEEKLY_MAX_DAYS else "month"
        totals: dict[date, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
        for r in counted:
            b = _bucket(r.date, granularity)
            if r.amount > 0 and r.category_id != refunds_id:
                totals[b][0] += r.amount
            elif r.amount > 0:
                totals[b][1] -= r.amount  # refund reduces that period's spending
            else:
                totals[b][1] += -r.amount
        b = _bucket(start, granularity)
        while b <= end:
            inc, spend = totals.get(b, [ZERO, ZERO])
            series.append(
                {
                    "start": b.isoformat(),
                    "label": _bucket_label(b, granularity),
                    "income": _money(inc),
                    "spending": _money(max(spend, ZERO)),
                }
            )
            b = _next_bucket(b, granularity)

    # ---- spending by category group (gross money out; refunds listed separately)
    by_group: dict[int | None, _Tally] = defaultdict(_Tally)
    for r in counted:
        if r.amount < 0:
            g = group_of(r.category_id)
            by_group[g.id if g is not None else None].add(-r.amount)
    ranked = sorted(by_group.items(), key=lambda kv: kv[1].amount, reverse=True)
    share = (lambda a: float(a / money_out)) if money_out else (lambda a: 0.0)
    by_category: list[dict[str, object]] = [
        {
            "category_id": key,
            "name": cats[key].name if key is not None else "Uncategorized",
            "amount": _money(t.amount),
            "count": t.count,
            "share": share(t.amount),
        }
        for key, t in ranked[:TOP_CATEGORIES]
    ]
    tail = ranked[TOP_CATEGORIES:]
    if tail:  # never a 9th color: the rest folds into "Other"
        other = sum((t.amount for _, t in tail), ZERO)
        by_category.append(
            {
                "category_id": None,
                "name": f"Other ({len(tail)})",
                "amount": _money(other),
                "count": sum(t.count for _, t in tail),
                "share": share(other),
                "is_other": True,
            }
        )

    # ---- top merchants by money out
    merch: dict[str, _Tally] = defaultdict(_Tally)
    for r in counted:
        if r.amount < 0 and r.merchant:
            merch[r.merchant].add(-r.amount, r.category_id)
    top_merchants = [
        {
            "merchant": name,
            "amount": _money(t.amount),
            "count": t.count,
            "category_id": t.category_id,
        }
        for name, t in sorted(merch.items(), key=lambda kv: kv[1].amount, reverse=True)[
            :TOP_MERCHANTS
        ]
    ]

    # ---- recurring payments: look back beyond the selected range, up to its end
    as_of = end or date.today()
    history = [
        r
        for r in _load_rows(
            db, user_id, account_id, as_of - timedelta(days=RECURRING_LOOKBACK_DAYS), as_of
        )
        if r.currency == chosen
    ]
    recurring = _detect_recurring(history, as_of)

    pie = _pie(db, user_id, counted, by_group, money_out, chosen, group_of)

    uncategorized = [r for r in counted if r.amount < 0 and r.category_id is None]
    return {
        "currency": chosen,
        "currencies": currencies,
        "period": {
            "date_from": start.isoformat() if start else None,
            "date_to": end.isoformat() if end else None,
            "granularity": granularity,
        },
        "summary": {
            "income": _money(income),
            "spending": _money(spending),
            "refunds": _money(refunds),
            "money_in": _money(money_in),
            "money_out": _money(money_out),
            "net": _money(net),
            "savings_rate": savings_rate,
            "transactions": len(counted),
            "excluded_transfers": len(rows) - len(counted),
            "uncategorized_count": len(uncategorized),
            "uncategorized_spend": _money(-sum((r.amount for r in uncategorized), ZERO)),
        },
        "series": series,
        "by_category": by_category,
        "pie": pie,
        "top_merchants": top_merchants,
        "recurring": recurring,
    }
