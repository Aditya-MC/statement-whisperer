from __future__ import annotations

import json
import logging
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.schemas.mapping import ColumnMapping
from app.services.llm import FakeLLMClient, LLMClient, UnavailableLLMClient

HEADER = ["Date", "Description", "Amount", "Balance"]
MAPPING = ColumnMapping(
    date_column=0, description_columns=[1], amount_mode="signed", amount_column=2,
    balance_column=3, date_format="%d/%m/%Y", currency="USD",
)  # fmt: skip

# A running ledger; statements are slices of it.
LEDGER: list[tuple[str, str, str]] = [
    ("01/02/2024", "PAYROLL ACME CORP", "2500.00"),
    ("03/02/2024", "COFFEE HOUSE", "-4.20"),
    ("03/02/2024", "COFFEE HOUSE", "-4.20"),
    ("05/02/2024", "GROCERY MART 22", "-82.15"),
    ("09/02/2024", "RENT JANE DOE", "-1200.00"),
    ("14/02/2024", "CITY POWER", "-64.90"),
    ("20/02/2024", "REFUND MEGASTORE", "35.00"),
    ("25/02/2024", "GYM MEMBERSHIP", "-40.00"),
    ("28/02/2024", "INTEREST", "1.12"),
]


def statement(start: int, end: int, opening: Decimal = Decimal("1000.00")) -> bytes:
    """CSV for LEDGER[start:end] with correct running balances."""
    bal = opening + sum((Decimal(a) for _, _, a in LEDGER[:start]), Decimal(0))
    lines = ["Example Bank statement", ",".join(HEADER)]
    for d, desc, amt in LEDGER[start:end]:
        bal += Decimal(amt)
        lines.append(f"{d},{desc},{amt},{bal}")
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture
def llm(fake_llm: FakeLLMClient) -> FakeLLMClient:
    fake_llm.register(HEADER, MAPPING)
    return fake_llm


@pytest.fixture
def account_id(client: TestClient) -> int:
    r = client.post(
        "/api/accounts",
        json={"bank_name": "Example", "nickname": "Checking", "currency": "usd", "last4": "4321"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["currency"] == "USD"
    return int(r.json()["id"])


def upload(client: TestClient, account_id: int, data: bytes, name: str = "s.csv", **form: str):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/imports",
        data={"account_id": str(account_id), **form},
        files={"file": (name, data, "text/csv")},
    )


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"


def test_full_account_number_is_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/accounts",
        json={"bank_name": "X", "nickname": "Y", "currency": "USD", "last4": "123456789012"},
    )
    assert r.status_code == 422


def test_upload_completes_and_lists_transactions(
    client: TestClient, account_id: int, llm: FakeLLMClient
) -> None:
    r = upload(client, account_id, statement(0, 9))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "completed", body
    assert body["inserted_count"] == 9 and body["duplicate_count"] == 0
    assert Decimal(body["opening_balance"]) == Decimal("1000.00")
    assert body["mapping_source"] == "llm"
    assert body["columns"] == HEADER

    page = client.get("/api/transactions", params={"account_id": account_id}).json()
    assert page["total"] == 9
    assert page["items"][0]["raw_narration"] == "INTEREST"  # newest first
    assert client.get(f"/api/imports/{body['id']}").json()["status"] == "completed"


def test_reupload_same_file_is_rejected(
    client: TestClient, account_id: int, llm: FakeLLMClient
) -> None:
    data = statement(0, 5)
    first = upload(client, account_id, data).json()
    r = upload(client, account_id, data)
    assert r.status_code == 409
    assert r.json()["existing_import_id"] == first["id"]


def test_overlapping_statements_do_not_duplicate(
    client: TestClient, account_id: int, llm: FakeLLMClient
) -> None:
    a = upload(client, account_id, statement(0, 6)).json()
    b = upload(client, account_id, statement(3, 9)).json()
    assert a["inserted_count"] == 6
    assert b["status"] == "completed"
    assert b["inserted_count"] == 3 and b["duplicate_count"] == 3
    assert client.get("/api/transactions", params={"account_id": account_id}).json()["total"] == 9


def test_same_day_identical_rows_are_both_kept(
    client: TestClient, account_id: int, llm: FakeLLMClient
) -> None:
    upload(client, account_id, statement(0, 4))
    items = client.get("/api/transactions", params={"account_id": account_id}).json()["items"]
    assert sum(1 for t in items if t["raw_narration"] == "COFFEE HOUSE") == 2


def test_wrong_mapping_needs_review_then_retry_fixes_it(
    client: TestClient, account_id: int, fake_llm: FakeLLMClient
) -> None:
    wrong = MAPPING.model_copy(update={"date_format": "%m/%d/%Y"})
    fake_llm.register(HEADER, wrong)
    data = statement(0, 9)
    r = upload(client, account_id, data).json()
    assert r["status"] == "needs_review"
    report = r["validation"]
    assert report["issue_counts"]["date_parse"] >= 1
    assert "%d/%m/%Y" in report["suggestions"]["date_format"]

    fixed = client.post(
        f"/api/imports/{r['id']}/retry",
        data={"mapping": MAPPING.model_dump_json()},
        files={"file": ("s.csv", data, "text/csv")},
    ).json()
    assert fixed["id"] == r["id"]
    assert fixed["status"] == "completed"
    assert fixed["mapping_source"] == "user"
    assert fixed["inserted_count"] == 9


def test_retry_requires_the_same_file(
    client: TestClient, account_id: int, fake_llm: FakeLLMClient
) -> None:
    fake_llm.register(HEADER, MAPPING.model_copy(update={"date_format": "%m/%d/%Y"}))
    r = upload(client, account_id, statement(0, 9)).json()
    resp = client.post(
        f"/api/imports/{r['id']}/retry",
        data={"mapping": MAPPING.model_dump_json()},
        files={"file": ("s.csv", statement(0, 8), "text/csv")},
    )
    assert resp.status_code == 400


def test_llm_unavailable_falls_back_to_manual_mapping(
    client: TestClient, account_id: int, llm_override: dict[str, LLMClient]
) -> None:
    llm_override["client"] = UnavailableLLMClient("ANTHROPIC_API_KEY is not set")
    data = statement(0, 9)
    r = upload(client, account_id, data).json()
    assert r["status"] == "needs_review"
    assert r["mapping"] is None
    assert r["columns"] == HEADER
    assert "ANTHROPIC_API_KEY" in r["error_message"]

    done = client.post(
        f"/api/imports/{r['id']}/retry",
        data={"mapping": MAPPING.model_dump_json()},
        files={"file": ("s.csv", data, "text/csv")},
    ).json()
    assert done["status"] == "completed"


def test_mapping_can_be_supplied_up_front(
    client: TestClient, account_id: int, llm_override: dict[str, LLMClient]
) -> None:
    llm_override["client"] = UnavailableLLMClient("offline")
    r = upload(client, account_id, statement(0, 9), mapping=MAPPING.model_dump_json())
    assert r.json()["status"] == "completed"


def test_invalid_mapping_json_is_422(client: TestClient, account_id: int) -> None:
    r = upload(client, account_id, statement(0, 3), mapping=json.dumps({"date_column": 0}))
    assert r.status_code == 422


def test_pdf_is_415(client: TestClient, account_id: int) -> None:
    r = upload(client, account_id, b"%PDF-1.7 fake", name="s.pdf")
    assert r.status_code == 415
    assert "PDF" in r.json()["detail"]


def test_unknown_account_is_404(client: TestClient) -> None:
    assert upload(client, 999, statement(0, 3)).status_code == 404


def test_upload_size_limit(
    client: TestClient, account_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    small = Settings(max_upload_mb=1, _env_file=None)  # type: ignore[call-arg]
    monkeypatch.setattr("app.api.imports.get_settings", lambda: small)
    r = upload(client, account_id, b"a" * (1024 * 1024 + 1))
    assert r.status_code == 413


def test_unreadable_file_is_marked_failed(
    client: TestClient, account_id: int, llm: FakeLLMClient
) -> None:
    r = upload(client, account_id, b"hello\nworld\n")
    assert r.status_code == 201
    assert r.json()["status"] == "failed"
    assert r.json()["error_message"]


def test_no_statement_content_in_logs(
    client: TestClient, account_id: int, llm: FakeLLMClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        upload(client, account_id, statement(0, 9))
    text = caplog.text
    assert "import id=" in text  # we do log metadata
    for _, desc, amt in LEDGER:
        assert desc not in text
        assert amt not in text


def iso_statement() -> bytes:
    """Same columns as `statement()` but ISO dates, so the saved dd/mm/yyyy mapping won't fit."""
    lines = ["Example Bank statement", ",".join(HEADER), "2024-03-01,LATE FEE,-5.00,995.00"]
    return ("\n".join(lines) + "\n").encode()


def test_saved_mapping_is_reused_without_llm(
    client: TestClient, account_id: int, llm_override: dict[str, LLMClient]
) -> None:
    llm_override["client"] = UnavailableLLMClient("offline")
    first = upload(client, account_id, statement(0, 5)).json()
    assert first["status"] == "needs_review"
    done = client.post(
        f"/api/imports/{first['id']}/retry",
        data={"mapping": MAPPING.model_dump_json()},
        files={"file": ("s.csv", statement(0, 5), "text/csv")},
    ).json()
    assert done["status"] == "completed"

    # Next month's statement from the same bank: imported straight through, no LLM needed.
    second = upload(client, account_id, statement(5, 9)).json()
    assert second["status"] == "completed"
    assert second["mapping_source"] == "saved"
    assert second["inserted_count"] == 4


def test_saved_mapping_works_across_accounts_with_same_layout(
    client: TestClient, account_id: int, llm_override: dict[str, LLMClient]
) -> None:
    upload(client, account_id, statement(0, 5), mapping=MAPPING.model_dump_json())
    llm_override["client"] = UnavailableLLMClient("offline")
    other = client.post(
        "/api/accounts", json={"bank_name": "Example", "nickname": "Joint", "currency": "USD"}
    ).json()["id"]
    r = upload(client, other, statement(0, 5)).json()
    assert r["status"] == "completed" and r["mapping_source"] == "saved"


def test_saved_mapping_that_no_longer_fits_falls_back_to_llm(
    client: TestClient, account_id: int, fake_llm: FakeLLMClient
) -> None:
    upload(client, account_id, statement(0, 5), mapping=MAPPING.model_dump_json())
    fake_llm.register(HEADER, MAPPING.model_copy(update={"date_format": "%Y-%m-%d"}))
    r = upload(client, account_id, iso_statement()).json()
    assert r["status"] == "completed"
    assert r["mapping_source"] == "llm"


def test_saved_mapping_misfit_offline_prefills_review(
    client: TestClient, account_id: int, llm_override: dict[str, LLMClient]
) -> None:
    upload(client, account_id, statement(0, 5), mapping=MAPPING.model_dump_json())
    llm_override["client"] = UnavailableLLMClient("offline")
    r = upload(client, account_id, iso_statement()).json()
    assert r["status"] == "needs_review"
    assert r["mapping_source"] == "saved"
    assert r["mapping"]["date_format"] == "%d/%m/%Y"  # review screen starts from it
    assert "%Y-%m-%d" in r["validation"]["suggestions"]["date_format"]
