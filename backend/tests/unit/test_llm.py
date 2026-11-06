from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings
from app.schemas.mapping import ColumnMapping, LLMColumnMapping
from app.services.llm import (
    AnthropicLLMClient,
    FakeLLMClient,
    LLMError,
    MerchantCategorization,
    MerchantCategory,
    UnavailableLLMClient,
    build_llm_client,
    render_schema_prompt,
)
from app.services.masking import build_masked_merchant, build_masked_sample

MAPPING = dict(
    date_column=0, description_columns=[1], amount_mode="signed", amount_column=2,
    balance_column=3, date_format="%d/%m/%Y", currency="INR",
)  # fmt: skip
SAMPLE = build_masked_sample(
    ["Date", "Narration", "Amount", "Balance"],
    [["05/01/2024", "UPI/412345678901/JANE DOE", "-1,200.00", "10,000.00"]],
)


class StubMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


def _client(
    response: Any, model: str = "claude-opus-5-5"
) -> tuple[AnthropicLLMClient, StubMessages]:
    msgs = StubMessages(response)
    sdk = SimpleNamespace(beta=SimpleNamespace(messages=msgs))
    return AnthropicLLMClient(api_key="test", model=model, sdk_client=sdk), msgs


def test_anthropic_client_sends_only_masked_sample() -> None:
    parsed = LLMColumnMapping(**MAPPING, notes="day-first")
    client, msgs = _client(SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))
    mapping = client.infer_schema(SAMPLE)

    assert mapping == ColumnMapping(**MAPPING)
    kw = msgs.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_format"] is LLMColumnMapping
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "medium"}
    content = kw["messages"][0]["content"]
    assert content == render_schema_prompt(SAMPLE)
    assert "JANE" not in content and "412345678901" not in content
    columns = json.loads(content)["columns"]
    assert columns[0] == {"index": 0, "header": "Date", "samples": ["05/01/2024"]}


def test_models_without_fallback_support_omit_beta() -> None:
    parsed = LLMColumnMapping(**MAPPING)
    client, msgs = _client(
        SimpleNamespace(stop_reason="end_turn", parsed_output=parsed), "claude-haiku-5-5"
    )
    client.infer_schema(SAMPLE)
    assert "betas" not in msgs.kwargs and "fallbacks" not in msgs.kwargs


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_anthropic_client_bad_stop_reasons(stop_reason: str) -> None:
    client, _ = _client(SimpleNamespace(stop_reason=stop_reason, parsed_output=None))
    with pytest.raises(LLMError):
        client.infer_schema(SAMPLE)


def test_fake_client_matches_on_masked_header() -> None:
    fake = FakeLLMClient()
    fake.register(["Date", "Narration", "Amount", "Balance"], ColumnMapping(**MAPPING))
    assert fake.infer_schema(SAMPLE).currency == "INR"
    assert fake.calls == [SAMPLE]
    with pytest.raises(LLMError):
        fake.infer_schema(build_masked_sample(["X", "Y", "Z"], []))


def test_build_llm_client_without_key_is_unavailable() -> None:
    client = build_llm_client(
        Settings(llm_provider="anthropic", anthropic_api_key=None, _env_file=None)
    )  # type: ignore[call-arg]
    assert isinstance(client, UnavailableLLMClient)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        client.infer_schema(SAMPLE)


def test_demo_mode_never_uses_network_client() -> None:
    client = build_llm_client(Settings(demo_mode=True, anthropic_api_key="sk-x", _env_file=None))  # type: ignore[call-arg]
    assert isinstance(client, FakeLLMClient)


class SeqMessages:
    """Stub returning a different response per call, recording every request."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_categorize_merchants_batches_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.llm.CATEGORIZE_BATCH_SIZE", 2)
    cats = ["Food > Groceries", "Other > Uncategorized"]
    names = ["SHOP A", "SHOP B", "SHOP C"]
    merchants = [
        build_masked_merchant(i, f"{name} 4111111111111111", "debit")
        for i, name in enumerate(names)
    ]
    ok = SimpleNamespace(
        stop_reason="end_turn",
        parsed_output=MerchantCategorization(
            results=[
                MerchantCategory(id=0, category="Food > Groceries"),
                MerchantCategory(id=1, category="Made Up > Category"),
                MerchantCategory(id=99, category="Food > Groceries"),  # id we never asked for
            ]
        ),
    )
    last = SimpleNamespace(stop_reason="end_turn", parsed_output=MerchantCategorization(results=[]))
    msgs = SeqMessages([ok, last])
    client = AnthropicLLMClient(
        api_key="t",
        model="claude-opus-5-5",
        sdk_client=SimpleNamespace(beta=SimpleNamespace(messages=msgs)),
    )

    out = client.categorize_merchants(merchants, cats)

    assert out == {0: "Food > Groceries", 1: "Other > Uncategorized", 2: "Other > Uncategorized"}
    assert len(msgs.calls) == 2
    payload = json.loads(msgs.calls[0]["messages"][0]["content"])
    assert payload["categories"] == cats
    assert payload["merchants"][0] == {
        "id": 0,
        "merchant": "SHOP A <num>",
        "direction": "debit",
        "hints": [],
    }
    assert msgs.calls[0]["output_format"] is MerchantCategorization
