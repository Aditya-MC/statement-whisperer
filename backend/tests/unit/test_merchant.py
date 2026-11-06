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


# --- Indian bank (IOB-style) formats: UPI/<ref>/<DR|CR>/<payee>/<bank>/<note> --------------
# All names, handles and reference numbers below are invented.


@pytest.mark.parametrize(
    ("narration", "merchant", "is_person"),
    [
        ("UPI/600000000001/DR/EXAMPLE STORES/YES/UPI", "EXAMPLE STORES", False),
        ("UPI/600000000002/DR/  Jane Doe Q/SBI/UPI", "JANE DOE Q", True),
        ("UPI/600000000003/CR/   JOHN  Q/SBI/UPI", "JOHN Q", True),
        ("UPI/600000000004/DR/  Mr EXAMPLE  N/YES/UPI", "MR EXAMPLE N", True),
        ("UPI/600000000005/DR/   EXAMPLEPAYEE/IOB/UPI", "EXAMPLEPAYEE", True),  # lone word
        ("UPI/600000000006/DR/9999999999@pty/IDI/UPI", "9999999999@PTY", True),  # handle
        ("UPI/600000000007/DR/janedoe.12-3@/IOB/UPI", "JANEDOE.12-3@", True),  # cut-off handle
        ("UPI/600000000008/DR/  N.Example  ./SBI/UPI", "N.EXAMPLE", True),
        # Bank cut the name at 14 chars: the last word is a business-word prefix.
        ("UPI/600000000009/DR/SRI SAI SERVIC/HDF/UPI", "SRI SAI SERVIC", False),
        ("UPI/600000000010/DR/KAVERI TRANSPO/UTI/UPI", "KAVERI TRANSPO", False),
        ("UPI/600000000011/DR/THIRUMALAI STO/FDR/Pay To TH", "THIRUMALAI STO", False),
        ("UPI/600000000012/DR/PUMP 14 EXAMPL /YES/UPI", "PUMP EXAMPL", False),
        ("UPI/600000000013/DR/Google India D/UTI/UPI", "GOOGLE INDIA D", False),
    ],
)
def test_upi_positional_payee(narration: str, merchant: str, is_person: bool) -> None:
    c = clean_merchant(narration)
    assert c.merchant == merchant
    assert c.is_person is is_person
    assert c.channel == "UPI"


def test_atm_with_reference_prefix() -> None:
    c = clean_merchant("600000000014-ATM-WSG EXAMPLEPURAM SOMECITY TNI")
    assert c.is_atm and c.merchant == "ATM WITHDRAWAL"


def test_neft_drops_ifsc_bank_code() -> None:
    c = clean_merchant("NEFT-ABCD-ABCDH12345678901-EXAMPLE EMPLOY-//ATTN")
    assert c.merchant == "EXAMPLE EMPLOY"


def test_pos_with_terminal_ids() -> None:
    c = clean_merchant("POS-1234 EXAMPLE MART SOMECITY TNIN-N000000O-")
    assert c.merchant == "EXAMPLE MART SOMECITY TNIN" and not c.is_person


def test_standing_instruction() -> None:
    assert clean_merchant("APY/SI/OCTOBER 2026").merchant == "APY"
