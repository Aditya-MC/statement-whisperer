"""Turn a raw bank narration into a short merchant name plus a few signals.

Examples:

    UPI/412345678901/SWIGGY/jdoe@okaxis/Payment  -> SWIGGY
    POS XXXX1234 SHELL FUEL STATION 22            -> SHELL FUEL STATION
    CARD XXXX9876 UBER TRIP HELP.UBER.COM         -> UBER TRIP
    NEFT CR-0012345678-ACME CORP-SALARY           -> ACME CORP  (keyword SALARY)
    ATM WDL 123456 MG ROAD BRANCH                 -> ATM WITHDRAWAL

The narration is split into segments on `/ - : | *`. Payment-channel words (UPI, NEFT,
POS...), reference numbers, masked card numbers and UPI handles are dropped. The first
segment with real words left is the merchant. Generic keywords such as SALARY or REFUND are
collected as hints for categorization. `is_person` flags person-to-person payments, whose
"merchant" is someone's name: those are never sent to the LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _words(text: str) -> frozenset[str]:
    """Whitespace-separated word list -> frozenset (keeps long lists readable)."""
    return frozenset(text.split())


CHANNEL_WORDS = _words(
    """UPI NEFT IMPS RTGS POS ATM ACH ECS NACH CARD BIL ONL BILLPAY TRF TFR TRANSFER INB MB
    NET BANKING DEBIT CREDIT DR CR PAYMENT PMT PURCHASE WDL CHQ CHEQUE PAID DEP INT PD REF TXN
    VPS IPS AUTOPAY SI MANDATE TO FROM BY VIA ON THE OF P2P P2M COLLECT REQ"""
)
#: Channels used for paying people (as opposed to card/merchant payments).
P2P_CHANNELS = frozenset({"IMPS", "NEFT", "RTGS", "UPI", "CHQ", "CHEQUE", "TRF", "TFR"})
#: Channel words too generic to identify the payment channel.
_GENERIC = frozenset(
    {"TO", "FROM", "BY", "VIA", "ON", "THE", "OF", "DR", "CR", "REF", "TXN", "PAID", "PD"}
)

#: Hint keywords: collected from the whole narration and passed to categorization.
KEYWORDS = _words(
    """SALARY SAL PAYROLL RENT REFUND REVERSAL CASHBACK INTEREST EMI LOAN SIP INSURANCE
    PREMIUM FEE FEES CHARGES CHARGE GST TAX DIVIDEND"""
)
#: Keywords that describe the payment rather than the merchant, removed from the name.
_DROP_FROM_NAME = frozenset({"SALARY", "SAL", "PAYROLL", "RENT", "REFUND", "REVERSAL", "CASHBACK"})

#: Words that mark an organization, so a 2-4 word name containing one isn't a person.
BUSINESS_WORDS = _words(
    """LTD LIMITED PVT PRIVATE CORP CORPORATION INC LLC LLP CO COMPANY STORE STORES MART
    MARKET MARKETPLACE SHOP SHOPPE SERVICES SERVICE SOLUTIONS TECHNOLOGIES TECH BANK FUND
    MUTUAL INSURANCE TELECOM POWER UTILITY UTILITIES ENERGY GAS WATER ELECTRIC ELECTRICITY
    HOSPITAL PHARMACY MEDICAL CLINIC RESTAURANT CAFE HOTEL FOODS FOOD TRAVELS TRAVEL AIRLINES
    AIRWAYS MOTORS AUTO FUEL STATION PETROL ENTERPRISES TRADERS AGENCY AGENCIES SCHOOL COLLEGE
    UNIVERSITY ACADEMY CENTRE CENTER GROUP INDUSTRIES INTERNATIONAL GLOBAL ONLINE RETAIL
    SUPERMARKET HYPERMARKET POSTPAID PREPAID BROADBAND CINEMAS MOVIES GYM FITNESS SAVINGS
    MEGASTORE TRIP POINT"""
)

_SEGMENT_SPLIT = re.compile(r"[/:|*]+|\s-\s|-(?=\S)|(?<=\S)-")
_MASKED_CARD = re.compile(r"^[X*]{2,}\d+$")
_NAME_TOKEN = re.compile(r"^[A-Z][A-Z.']{0,14}$")
_MAX_LEN = 60


@dataclass(frozen=True)
class CleanMerchant:
    merchant: str
    channel: str | None = None
    keywords: frozenset[str] = field(default_factory=frozenset)
    is_person: bool = False
    is_atm: bool = False


def _domain_label(token: str) -> str:
    """HELP.UBER.COM -> UBER, NETFLIX.COM -> NETFLIX, INT.PD -> INT."""
    labels = [p for p in token.split(".") if p]
    if len(labels) >= 2:
        return labels[-2] if len(labels[-1]) <= 3 else labels[0]
    return labels[0] if labels else ""


def _is_noise(token: str) -> bool:
    if not token or token in CHANNEL_WORDS:
        return True
    if "@" in token or _MASKED_CARD.match(token):
        return True
    digits = sum(ch.isdigit() for ch in token)
    if digits and digits / len(token) >= 0.5:  # reference numbers, 22, 0012345
        return True
    return not any(ch.isalpha() for ch in token)


def _clean_segment(segment: str) -> list[str]:
    out: list[str] = []
    for raw in segment.split():
        token = raw.strip(".,;#()[]{}'\"")
        if "." in token and any(ch.isalpha() for ch in token):
            token = _domain_label(token)
        if _is_noise(token) or token in _DROP_FROM_NAME:
            continue
        if token not in out:  # "UBER TRIP UBER" -> "UBER TRIP"
            out.append(token)
    return out


def _looks_like_person(tokens: list[str]) -> bool:
    if not 2 <= len(tokens) <= 4:
        return False
    if any(t in BUSINESS_WORDS or t in KEYWORDS for t in tokens):
        return False
    return all(_NAME_TOKEN.match(t) for t in tokens)


def clean_merchant(narration: str) -> CleanMerchant:
    text = " ".join(narration.upper().split())
    all_tokens = re.findall(r"[A-Z]+", text)
    keywords = frozenset(t for t in all_tokens if t in KEYWORDS)
    channel = next((t for t in all_tokens if t in CHANNEL_WORDS and t not in _GENERIC), None)

    atm_words = {"WDL", "WITHDRAWAL", "CASH"} & set(all_tokens)
    if "ATM" in all_tokens and (atm_words or text.startswith("ATM")):
        return CleanMerchant("ATM WITHDRAWAL", "ATM", keywords, is_atm=True)

    merchant_tokens: list[str] = []
    for segment in _SEGMENT_SPLIT.split(text):
        tokens = _clean_segment(segment)
        if tokens and sum(len(t) for t in tokens) >= 2:
            merchant_tokens = tokens
            break

    if not merchant_tokens:
        fallback = sorted(keywords)[0] if keywords else "UNKNOWN"
        return CleanMerchant(fallback, channel, keywords)

    merchant = " ".join(merchant_tokens)[:_MAX_LEN].strip()
    is_person = channel in P2P_CHANNELS and _looks_like_person(merchant_tokens)
    return CleanMerchant(merchant, channel, keywords, is_person=is_person)
