from __future__ import annotations

import pytest

from app.categorization.merchant import clean_merchant


@pytest.mark.parametrize(
    ("narration", "merchant"),
    [
        ("UPI/412345678901/SWIGGY/jdoe@okaxis/Payment", "SWIGGY"),
        ("UPI/412345678901/ZEPTO MARKETPLACE/store77@ybl", "ZEPTO MARKETPLACE"),
        ("POS XXXX1234 AMAZON MKTPLACE SEATTLE", "AMAZON MKTPLACE SEATTLE"),
        ("POS XXXX1234 SHELL FUEL STATION 22", "SHELL FUEL STATION"),
        ("CARD XXXX9876 UBER TRIP HELP.UBER.COM", "UBER TRIP"),
        ("ACH DEBIT NETFLIX.COM 5566778899", "NETFLIX"),
        ("NEFT CR-0012345678-ACME CORP-SALARY", "ACME CORP"),
        ("NEFT DR-0012345678-CITY POWER UTILITY", "CITY POWER UTILITY"),
        ("BIL/ONL/0012345678/ACME TELECOM POSTPAID", "ACME TELECOM POSTPAID"),
        ("INT.PD:0012345678:SAVINGS INTEREST", "SAVINGS INTEREST"),
        ("UPI/0012345678/REFUND MEGASTORE/pay.merchant@okexample", "MEGASTORE"),
        ("SIP 0012345678 EXAMPLE MUTUAL FUND", "SIP EXAMPLE MUTUAL FUND"),
        ("  pos*Coffee   Shop  ", "COFFEE SHOP"),
        ("0012345678", "UNKNOWN"),
    ],
)
def test_clean_merchant(narration: str, merchant: str) -> None:
    assert clean_merchant(narration).merchant == merchant


def test_atm_withdrawal() -> None:
    c = clean_merchant("ATM WDL 0012345678 MG ROAD BRANCH")
    assert c.merchant == "ATM WITHDRAWAL" and c.is_atm


def test_keywords_collected() -> None:
    assert clean_merchant("NEFT CR-0012345678-ACME CORP-SALARY").keywords == {"SALARY"}
    assert "INTEREST" in clean_merchant("INT.PD:0012345678:SAVINGS INTEREST").keywords


@pytest.mark.parametrize(
    "narration",
    ["IMPS-0012345678-JANE DOE-RENT", "CHQ PAID 0012345678 JOHN Q PUBLIC",
     "UPI/0012345678/JOHN Q PUBLIC/jqp@okaxis"],
)  # fmt: skip
def test_person_payments_are_flagged(narration: str) -> None:
    assert clean_merchant(narration).is_person


@pytest.mark.parametrize(
    "narration",
    ["UPI/0012345678/SWIGGY/jdoe@okaxis", "UPI/0012345678/CHAI POINT/jdoe@ybl",
     "NEFT CR-0012345678-ACME CORP-SALARY", "POS XXXX1234 JOHN SMITH",  # card payment, not P2P
     "NEFT DR-0012345678-CITY POWER UTILITY"],
)  # fmt: skip
def test_merchants_are_not_people(narration: str) -> None:
    assert not clean_merchant(narration).is_person
