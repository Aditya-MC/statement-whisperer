from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.llm import FakeLLMClient
from tests.api.test_api import HEADER, MAPPING, upload
from tests.api.test_categorize_api import categories, csv_statement, make_account, txns


def group_id(client: TestClient, name: str) -> int:
    return next(
        c["id"]
        for c in client.get("/api/categories").json()
        if c["name"] == name and c["parent_id"] is None
    )


def test_create_child_inherits_kind_and_group(client: TestClient) -> None:
    food = group_id(client, "Food")
    r = client.post(
        "/api/categories", json={"name": "  Street   food ", "parent_id": food, "kind": "income"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body == {
        **body,
        "name": "Street food",
        "parent_id": food,
        "kind": "expense",
        "is_custom": True,
    }
    assert "Food > Street food" in categories(client)


def test_create_new_group_and_child(client: TestClient) -> None:
    g = client.post("/api/categories", json={"name": "Pets", "kind": "expense"}).json()
    assert g["parent_id"] is None and g["is_custom"] is True
    c = client.post("/api/categories", json={"name": "Vet", "parent_id": g["id"]})
    assert c.status_code == 201
    assert "Pets > Vet" in categories(client)


def test_create_validation(client: TestClient) -> None:
    food = group_id(client, "Food")
    groceries = categories(client)["Food > Groceries"]
    assert (
        client.post("/api/categories", json={"name": "groceries", "parent_id": food}).status_code
        == 409
    )
    assert client.post("/api/categories", json={"name": "FOOD"}).status_code == 409  # top-level dup
    assert (
        client.post("/api/categories", json={"name": "X", "parent_id": groceries}).status_code
        == 422
    )
    assert client.post("/api/categories", json={"name": "A > B"}).status_code == 422
    assert client.post("/api/categories", json={"name": "   "}).status_code == 422


def test_built_in_categories_are_protected(client: TestClient) -> None:
    groceries = categories(client)["Food > Groceries"]
    assert client.patch(f"/api/categories/{groceries}", json={"name": "Shops"}).status_code == 403
    assert client.delete(f"/api/categories/{groceries}").status_code == 403


def test_rename_custom(client: TestClient) -> None:
    c = client.post("/api/categories", json={"name": "Pets"}).json()
    r = client.patch(f"/api/categories/{c['id']}", json={"name": "Pet care"})
    assert r.status_code == 200 and r.json()["name"] == "Pet care"


def test_delete_custom_uncategorizes_and_removes_rules(
    client: TestClient, fake_llm: FakeLLMClient
) -> None:
    fake_llm.register(HEADER, MAPPING)
    acct = make_account(client)
    rows = [
        ("01/03/2024", "POS XXXX1234 HAPPY PAWS", "-30.00"),
        ("02/03/2024", "POS XXXX1234 HAPPY PAWS", "-20.00"),
    ]
    upload(client, acct, csv_statement(rows))
    pets = client.post("/api/categories", json={"name": "Pets"}).json()
    vet = client.post("/api/categories", json={"name": "Vet", "parent_id": pets["id"]}).json()
    t = txns(client)[0]
    client.patch(f"/api/transactions/{t['id']}", json={"category_id": vet["id"]})  # creates a rule
    assert all(x["category_id"] == vet["id"] for x in txns(client))

    r = client.delete(f"/api/categories/{pets['id']}")  # deleting the group takes its children
    assert r.status_code == 200
    assert r.json() == {"transactions_uncategorized": 2, "rules_removed": 1}
    assert all(x["category_id"] is None for x in txns(client))
    assert "Pets > Vet" not in categories(client)
    assert [
        x for x in client.get("/api/merchant-rules").json() if x["pattern"] == "HAPPY PAWS"
    ] == []


def test_llm_can_choose_custom_categories(client: TestClient, fake_llm: FakeLLMClient) -> None:
    fake_llm.register(HEADER, MAPPING)
    pets = client.post("/api/categories", json={"name": "Pets"}).json()
    client.post("/api/categories", json={"name": "Vet", "parent_id": pets["id"]})
    fake_llm.register_merchant("HAPPY PAWS", "Pets > Vet")
    acct = make_account(client)
    upload(client, acct, csv_statement([("01/03/2024", "POS XXXX1234 HAPPY PAWS", "-30.00")]))
    # The fake only accepts answers from the category list it was given, so landing in
    # "Pets > Vet" proves the custom category was in the fixed list sent to the LLM.
    assert txns(client)[0]["category_id"] == categories(client)["Pets > Vet"]
