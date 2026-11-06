from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.llm import FakeLLMClient
from tests.api.test_api import HEADER, MAPPING, upload


def csv_statement(rows: list[tuple[str, str, str]], opening: str = "1000.00") -> bytes:
    from decimal import Decimal

    bal = Decimal(opening)
    lines = [",".join(HEADER)]
    for d, desc, amt in rows:
        bal += Decimal(amt)
        lines.append(f"{d},{desc},{amt},{bal}")
    return ("\n".join(lines) + "\n").encode()


ROWS = [
    ("01/03/2024", "NEFT CR-0012345678-ACME CORP-SALARY", "2500.00"),
    ("02/03/2024", "UPI/0012345678/SWIGGY/jdoe@okaxis", "-18.50"),
    ("03/03/2024", "POS XXXX1234 CORNER BAKERY", "-6.25"),
    ("04/03/2024", "POS XXXX5678 CORNER BAKERY", "-4.75"),
    ("05/03/2024", "IMPS-0012345678-JOHN Q PUBLIC-SPLIT", "-40.00"),
]


@pytest.fixture
def llm(fake_llm: FakeLLMClient) -> FakeLLMClient:
    fake_llm.register(HEADER, MAPPING)
    return fake_llm


def make_account(client: TestClient, nickname: str = "Checking") -> int:
    r = client.post(
        "/api/accounts", json={"bank_name": "B", "nickname": nickname, "currency": "USD"}
    )
    return int(r.json()["id"])


def categories(client: TestClient) -> dict[str, int]:
    cats = client.get("/api/categories").json()
    by_id = {c["id"]: c for c in cats}
    return {
        f"{by_id[c['parent_id']]['name']} > {c['name']}": c["id"] for c in cats if c["parent_id"]
    }


def txns(client: TestClient, **params: object) -> list[dict]:  # type: ignore[type-arg]
    return client.get("/api/transactions", params={"limit": 1000, **params}).json()["items"]


def test_import_categorizes_automatically(client: TestClient, llm: FakeLLMClient) -> None:
    acct = make_account(client)
    assert upload(client, acct, csv_statement(ROWS)).json()["status"] == "completed"
    cats = categories(client)
    by_merchant = {t["cleaned_merchant"]: t for t in txns(client)}
    assert by_merchant["SWIGGY"]["category_id"] == cats["Food > Food Delivery"]
    assert by_merchant["ACME CORP"]["category_id"] == cats["Income > Salary"]
    assert by_merchant["JOHN Q PUBLIC"]["category_id"] == cats["Transfers > Transfer to Others"]
    assert by_merchant["CORNER BAKERY"]["category_source"] == "llm"  # fake says Uncategorized
    sent = {m.merchant for batch in llm.merchant_calls for m in batch}
    assert sent == {"CORNER BAKERY"}


def test_correction_saves_rule_and_updates_similar(client: TestClient, llm: FakeLLMClient) -> None:
    acct = make_account(client)
    upload(client, acct, csv_statement(ROWS))
    cats = categories(client)
    bakery = [t for t in txns(client) if t["cleaned_merchant"] == "CORNER BAKERY"]

    r = client.patch(
        f"/api/transactions/{bakery[0]['id']}", json={"category_id": cats["Food > Groceries"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transaction"]["category_source"] == "user"
    assert body["updated_similar"] == 1

    after = {t["id"]: t for t in txns(client)}
    assert after[bakery[1]["id"]]["category_id"] == cats["Food > Groceries"]
    rules = client.get("/api/merchant-rules", params={"source": "user"}).json()
    assert [r["pattern"] for r in rules] == ["CORNER BAKERY"]

    grocery_rows = txns(client, category_id=cats["Food > Groceries"])
    assert len(grocery_rows) == 2


def test_parent_category_filter_and_search(client: TestClient, llm: FakeLLMClient) -> None:
    acct = make_account(client)
    upload(client, acct, csv_statement(ROWS))
    food_group = next(
        c["id"]
        for c in client.get("/api/categories").json()
        if c["name"] == "Food" and c["parent_id"] is None
    )
    assert {t["cleaned_merchant"] for t in txns(client, category_id=food_group)} == {"SWIGGY"}
    assert len(txns(client, q="bakery")) == 2
    assert len(txns(client, q="100%")) == 0  # wildcards are escaped


def test_unknown_category_is_422(client: TestClient, llm: FakeLLMClient) -> None:
    acct = make_account(client)
    upload(client, acct, csv_statement(ROWS))
    t = txns(client)[0]
    assert (
        client.patch(f"/api/transactions/{t['id']}", json={"category_id": 99999}).status_code == 422
    )


def test_recategorize_endpoint_and_rule_delete(client: TestClient, llm: FakeLLMClient) -> None:
    acct = make_account(client)
    upload(client, acct, csv_statement(ROWS))
    llm.register_merchant("CORNER BAKERY", "Food > Restaurants")
    r = client.post("/api/categorize", json={"account_id": acct}).json()
    assert r["processed"] == 5 and r["llm_merchants"] == 1 and r["llm_error"] is None
    cats = categories(client)
    bakery = [t for t in txns(client) if t["cleaned_merchant"] == "CORNER BAKERY"]
    assert all(t["category_id"] == cats["Food > Restaurants"] for t in bakery)

    rule = next(
        x
        for x in client.get("/api/merchant-rules", params={"source": "llm"}).json()
        if x["pattern"] == "CORNER BAKERY"
    )
    assert client.delete(f"/api/merchant-rules/{rule['id']}").status_code == 204
    assert client.delete(f"/api/merchant-rules/{rule['id']}").status_code == 404


def test_transfer_detected_across_accounts_and_unlink(
    client: TestClient, llm: FakeLLMClient
) -> None:
    checking, savings = make_account(client, "Checking"), make_account(client, "Savings")
    upload(
        client,
        checking,
        csv_statement([("10/03/2024", "NEFT DR-0012345678-TO SAVINGS", "-300.00")]),
    )
    upload(
        client,
        savings,
        csv_statement([("11/03/2024", "NEFT CR-0012345678-FROM CHECKING", "300.00")]),
    )
    cats = categories(client)
    pair = txns(client, is_transfer=True)
    assert len(pair) == 2
    assert all(t["category_id"] == cats["Transfers > Self Transfer"] for t in pair)

    r = client.patch(f"/api/transactions/{pair[0]['id']}", json={"is_transfer": False}).json()
    assert r["transaction"]["is_transfer"] is False
    assert txns(client, is_transfer=True) == []
    # A re-run must not link the dismissed pair again.
    assert client.post("/api/categorize", json={}).json()["transfers_linked"] == 0
