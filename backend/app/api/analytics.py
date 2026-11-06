from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.analytics import dashboard
from app.db import get_db

router = APIRouter(tags=["analytics"])


@router.get("/analytics/dashboard")
def get_dashboard(
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: int | None = None,
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Everything the dashboard shows for one filter slice (definitions: app/analytics.py)."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "date_from is after date_to")
    return dashboard(
        db, account_id=account_id, date_from=date_from, date_to=date_to, currency=currency
    )
