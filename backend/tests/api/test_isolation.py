"""One user must never see, change or use another user's data, through any endpoint.

`client` is the owner, who imports a statement, creates a custom category and a rule.
`other_client` is a second signed-in user, who then tries everything.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.llm import FakeLLMClient
from tests.api.test_api import HEADER, MAPPING, statement, upload


@pytest.fixture
def owner_data(client: TestClient, fake_llm: FakeLLMClient) -> dict[str, int]:
    fake_llm.register(HEADER, MAPPING)
    acct = client.post(
        "/api/accounts", json={"bank_name": "A", "nickname": "Mine", "currency": "USD"}
    ).json()
    imp = upload(client, acct["id"], statement(0, 9)).json()
    assert imp["status"] == "completed"
    txn = client.get("/api/transactions").json()["items"][0]
    pets = client.post("/api/categories", json={"name": "Pets"}).json()
    client.patch(f"/api/transactions/{txn['id']}", json={"category_id": pets["id"]})  # makes a rule
    rule = next(r for r in client.get("/api/merchant-rules", params={"source": "user"}).json())
    return {
        "account": acct["id"],
        "import": imp["id"],
        "txn": txn["id"],
        "category": pets["id"],
        "rule": rule["id"],
    }


def test_lists_show_nothing_of_others(owner_data: dict[str, int], other_client: TestClient) -> None:
    assert other_client.get("/api/accounts").json() == []
    assert other_client.get("/api/imports").json() == []
    assert other_client.get("/api/transactions").json() == {"total": 0, "items": []}
    assert (
        other_client.get("/api/transactions", params={"account_id": owner_data["account"]}).json()[
            "total"
        ]
        == 0
    )
    names = {c["name"] for c in other_client.get("/api/categories").json()}
    assert "Pets" not in names and "Food" in names  # built-ins shared, custom private
    rules = other_client.get("/api/merchant-rules").json()
    assert all(r["source"] == "seed" for r in rules)
    dash = other_client.get("/api/analytics/dashboard").json()
    assert dash["summary"]["transactions"] == 0 and dash["currencies"] == []


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/imports/{import}", None),
        ("PATCH", "/api/transactions/{txn}", {"category_id": 1}),
        ("PATCH", "/api/categories/{category}", {"name": "Stolen"}),
        ("DELETE", "/api/categories/{category}", None),
        ("DELETE", "/api/merchant-rules/{rule}", None),
        ("GET", "/api/analytics/dashboard?account_id={account}", None),
        ("POST", "/api/categorize", {"account_id": "{account}"}),
    ],
)
def test_direct_access_to_others_ids_is_not_found(
    owner_data: dict[str, int],
    other_client: TestClient,
    method: str,
    path: str,
    body: dict | None,  # type: ignore[type-arg]
) -> None:
    url = path.format(**owner_data)
    if body is not None:
        body = {k: (owner_data["account"] if v == "{account}" else v) for k, v in body.items()}
    r = other_client.request(method, url, json=body)
    assert r.status_code == 404, (method, url, r.status_code, r.text)


def test_cannot_upload_into_or_retry_others(
    owner_data: dict[str, int], other_client: TestClient
) -> None:
    assert upload(other_client, owner_data["account"], statement(0, 3)).status_code == 404
    r = other_client.post(
        f"/api/imports/{owner_data['import']}/retry",
        files={"file": ("s.csv", statement(0, 3), "text/csv")},
    )
    assert r.status_code == 404


def test_cannot_use_others_custom_category(
    owner_data: dict[str, int], other_client: TestClient, fake_llm: FakeLLMClient
) -> None:
    acct = other_client.post(
        "/api/accounts", json={"bank_name": "B", "nickname": "Theirs", "currency": "USD"}
    ).json()
    upload(other_client, acct["id"], statement(0, 3))
    txn = other_client.get("/api/transactions").json()["items"][0]
    r = other_client.patch(
        f"/api/transactions/{txn['id']}", json={"category_id": owner_data["category"]}
    )
    assert r.status_code == 422
    r = other_client.post(
        "/api/categories", json={"name": "Vet", "parent_id": owner_data["category"]}
    )
    assert r.status_code == 422


def test_same_category_name_allowed_for_different_users(
    owner_data: dict[str, int], other_client: TestClient
) -> None:
    assert other_client.post("/api/categories", json={"name": "Pets"}).status_code == 201


def test_rules_and_corrections_stay_private(
    owner_data: dict[str, int], client: TestClient, other_client: TestClient
) -> None:
    """The owner's correction must not recategorize the other user's identical merchant."""
    acct = other_client.post(
        "/api/accounts", json={"bank_name": "B", "nickname": "Theirs", "currency": "USD"}
    ).json()
    upload(other_client, acct["id"], statement(0, 9))
    pets = {c["id"] for c in client.get("/api/categories").json() if c["name"] == "Pets"}
    assert all(
        t["category_id"] not in pets for t in other_client.get("/api/transactions").json()["items"]
    )


def test_transfers_never_link_across_users(
    client: TestClient, other_client: TestClient, fake_llm: FakeLLMClient
) -> None:
    from tests.api.test_categorize_api import csv_statement

    fake_llm.register(HEADER, MAPPING)
    a = client.post(
        "/api/accounts", json={"bank_name": "A", "nickname": "A1", "currency": "USD"}
    ).json()
    b = other_client.post(
        "/api/accounts", json={"bank_name": "B", "nickname": "B1", "currency": "USD"}
    ).json()
    upload(
        client, a["id"], csv_statement([("10/03/2024", "NEFT DR-0012345678-TO FRIEND", "-300.00")])
    )
    upload(
        other_client,
        b["id"],
        csv_statement([("11/03/2024", "NEFT CR-0012345678-FROM FRIEND", "300.00")]),
    )
    assert client.get("/api/transactions", params={"is_transfer": True}).json()["total"] == 0
    assert other_client.get("/api/transactions", params={"is_transfer": True}).json()["total"] == 0
