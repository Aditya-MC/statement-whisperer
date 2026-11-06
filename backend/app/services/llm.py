"""The single gateway to any LLM.

Nothing else in the codebase imports an LLM SDK. Everything here takes already-masked input
(`MaskedSample`, `MaskedMerchant`), so swapping providers or mocking in tests is a matter of
providing another `LLMClient` implementation.

Two tasks:

* `infer_schema`: column mapping from a masked header and sample rows (Phase 1).
* `categorize_merchants`: one category per cleaned merchant name, chosen from the fixed
  category list and batched (Phase 2).

Implementations:

* `AnthropicLLMClient` - Claude via the official SDK with structured (JSON-schema) output.
* `FakeLLMClient` - deterministic and offline. Answers from registered mappings and merchants.
  Used by tests and demo mode.
* `UnavailableLLMClient` - used when no API key is configured. Every call raises `LLMError`.
  Imports then land in "needs review" and merchants stay uncategorized until rules cover them.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.schemas.mapping import ColumnMapping, LLMColumnMapping
from app.services.masking import MaskedMerchant, MaskedSample, mask_header

log = logging.getLogger(__name__)
_T = TypeVar("_T", bound=BaseModel)

#: Models that accept the server-side refusal fallback (`fallbacks: "default"`).
_FALLBACK_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
)
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

SCHEMA_SYSTEM_PROMPT = """\
You identify the column layout of a bank statement table so that a program can parse it.

You receive the table's header and a few sample values per column. Free text (narrations, names) \
has been replaced by placeholders like <text:42>, and long identifiers by <digits:N>. Dates, \
amounts and short debit/credit words are shown as they appear.

Work out:
- date_column: the transaction or posting date. If there is also a value date, prefer the \
transaction/posting date.
- description_columns: the narration/particulars column(s). Do not include reference or cheque \
number columns unless there is no other text column.
- amount_mode:
  - "debit_credit" when there are separate money-out (withdrawal/debit/paid out) and money-in \
(deposit/credit/paid in) columns.
  - "signed" when a single amount column carries direction by sign, parentheses, a trailing \
minus, or Dr/Cr markers.
  - "amount_with_type" when a single unsigned amount column is paired with a separate column \
saying debit/credit (DR/CR, D/C, Debit/Credit).
- balance_column if there is a running balance, otherwise null.
- date_format as a Python strptime format matching the sample dates exactly (e.g. %d/%m/%Y, \
%m/%d/%Y, %Y-%m-%d, %d-%b-%y, %d %b %Y). Use the sample values to disambiguate day/month order: \
a first number above 12 means day-first. If still ambiguous, prefer the convention implied by \
the currency and header language.
- decimal_separator and thousands_separator from the amounts (e.g. 1.234,56 means decimal "," \
and thousands "."; 1'234.50 means thousands "'"). Use "" when amounts never show grouping.
- currency as an ISO 4217 code, from symbols, codes, or header text. Pick the most plausible if \
not shown.
- sign_convention: "negative_is_debit" for normal bank statements; "positive_is_debit" only if \
the layout clearly lists spending as positive numbers (typical for credit-card statements).
- drcr_markers: true if amount or balance values carry Dr/Cr suffixes or prefixes.

Column indexes are 0-based. Use only columns that exist. Keep notes under 200 characters.\
"""


class LLMError(RuntimeError):
    """Any failure to get a usable answer from the LLM. Messages never contain statement data."""


class LLMClient(Protocol):
    def infer_schema(self, sample: MaskedSample) -> ColumnMapping:
        """Return a column mapping for the masked sample, or raise `LLMError`."""
        ...

    def categorize_merchants(
        self, merchants: Sequence[MaskedMerchant], categories: Sequence[str]
    ) -> dict[int, str]:
        """Map each merchant id to one of `categories` (exact strings), or raise `LLMError`."""
        ...


CATEGORIZE_BATCH_SIZE = 50
UNCATEGORIZED = "Other > Uncategorized"

CATEGORIZE_SYSTEM_PROMPT = f"""\
You categorize bank transactions for a personal finance ledger.

You receive a list of allowed categories and a list of merchants. Each merchant has an id, a \
cleaned merchant name taken from a bank statement (identifiers masked as <num>, <upi>, \
<email>), the direction ("debit" = money out, "credit" = money in), and optional hint keywords \
found in the original narration (e.g. SALARY, REFUND, EMI).

Return exactly one category per merchant id. The category must be copied exactly from the \
allowed list. Use the direction: money in is usually Income or a refund, money out is usually \
an expense. If you are not reasonably confident, use "{UNCATEGORIZED}". Do not invent \
categories.\
"""


class MerchantCategory(BaseModel):
    id: int
    category: str


class MerchantCategorization(BaseModel):
    results: list[MerchantCategory]


def render_categorize_prompt(merchants: Sequence[MaskedMerchant], categories: Sequence[str]) -> str:
    payload = {
        "categories": list(categories),
        "merchants": [
            {"id": m.id, "merchant": m.merchant, "direction": m.direction, "hints": list(m.hints)}
            for m in merchants
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1)


def _validate_categories(
    parsed: MerchantCategorization,
    batch: Sequence[MaskedMerchant],
    categories: Sequence[str],
) -> dict[int, str]:
    """Keep answers for ids we asked about; anything outside the fixed list is Uncategorized."""
    allowed = set(categories)
    wanted = {m.id for m in batch}
    out = {r.id: (r.category if r.category in allowed else UNCATEGORIZED) for r in parsed.results}
    return {i: out.get(i, UNCATEGORIZED) for i in wanted}


def render_schema_prompt(sample: MaskedSample) -> str:
    """Column-oriented JSON view of the masked sample (easier for the model than raw rows)."""
    columns = [
        {
            "index": i,
            "header": header,
            "samples": [row[i] for row in sample.rows if i < len(row)],
        }
        for i, header in enumerate(sample.header)
    ]
    return json.dumps({"columns": columns}, ensure_ascii=False, indent=1)


class AnthropicLLMClient:
    """Claude-backed client. Uses `messages.parse` so output is validated against the schema."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        effort: str = "medium",
        timeout: float = 60.0,
        sdk_client: Any | None = None,
    ) -> None:
        if sdk_client is None:
            import anthropic

            sdk_client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self._client = sdk_client
        self._model = model
        self._effort = effort

    def infer_schema(self, sample: MaskedSample) -> ColumnMapping:
        parsed = self._parse(SCHEMA_SYSTEM_PROMPT, render_schema_prompt(sample), LLMColumnMapping)
        log.info("schema inferred by LLM model=%s", self._model)
        return parsed.to_mapping()

    def categorize_merchants(
        self, merchants: Sequence[MaskedMerchant], categories: Sequence[str]
    ) -> dict[int, str]:
        results: dict[int, str] = {}
        for start in range(0, len(merchants), CATEGORIZE_BATCH_SIZE):
            batch = merchants[start : start + CATEGORIZE_BATCH_SIZE]
            parsed = self._parse(
                CATEGORIZE_SYSTEM_PROMPT,
                render_categorize_prompt(batch, categories),
                MerchantCategorization,
            )
            results.update(_validate_categories(parsed, batch, categories))
        log.info("categorized %s merchants via LLM model=%s", len(results), self._model)
        return results

    def _parse(self, system: str, content: str, output_format: type[_T]) -> _T:
        """One structured-output request with uniform error handling."""
        import anthropic

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "output_format": output_format,
            "output_config": {"effort": self._effort},
        }
        if self._model in _FALLBACK_MODELS:
            # On a policy refusal the API re-runs the request on a suitable fallback model.
            kwargs["betas"] = [_FALLBACK_BETA]
            kwargs["fallbacks"] = "default"

        try:
            response = self._client.beta.messages.parse(**kwargs)
        except ValidationError as exc:
            raise LLMError("LLM returned output that failed validation") from exc
        except anthropic.AuthenticationError as exc:
            raise LLMError("LLM authentication failed - check ANTHROPIC_API_KEY") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("LLM rate limit reached - try again shortly") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"LLM request failed with HTTP {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the LLM API") from exc

        if response.stop_reason == "refusal":
            raise LLMError("LLM declined the request")
        if response.stop_reason == "max_tokens":
            raise LLMError("LLM response was truncated")
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError("LLM returned no structured output")
        return parsed


def header_key(header: Iterable[str]) -> tuple[str, ...]:
    return tuple(" ".join(h.lower().split()) for h in header)


class FakeLLMClient:
    """Offline client that returns pre-registered mappings, looked up by (masked) header.

    `calls` records every sample it received so tests can assert what would have been sent.
    """

    def __init__(self, mappings: dict[tuple[str, ...], ColumnMapping] | None = None) -> None:
        self._mappings: dict[tuple[str, ...], ColumnMapping] = {}
        self._merchant_categories: dict[str, str] = {}
        self.calls: list[MaskedSample] = []
        self.merchant_calls: list[list[MaskedMerchant]] = []
        for header, mapping in (mappings or {}).items():
            self.register(header, mapping)

    def register_merchant(self, merchant: str, category: str) -> None:
        self._merchant_categories[merchant.upper()] = category

    def categorize_merchants(
        self, merchants: Sequence[MaskedMerchant], categories: Sequence[str]
    ) -> dict[int, str]:
        self.merchant_calls.append(list(merchants))
        allowed = set(categories)
        out: dict[int, str] = {}
        for m in merchants:
            category = self._merchant_categories.get(m.merchant.upper(), UNCATEGORIZED)
            out[m.id] = category if category in allowed else UNCATEGORIZED
        return out

    def register(self, header: Iterable[str], mapping: ColumnMapping) -> None:
        # Lookups happen on the masked header (all the client ever sees), so mask here too.
        self._mappings[header_key(mask_header(h) for h in header)] = mapping

    def infer_schema(self, sample: MaskedSample) -> ColumnMapping:
        self.calls.append(sample)
        try:
            return self._mappings[header_key(sample.header)]
        except KeyError:
            raise LLMError("Fake LLM has no mapping for this layout") from None

    @classmethod
    def from_samples_dir(cls, directory: Path) -> FakeLLMClient:
        """Load mappings from synthetic ground-truth files (`*.truth.json`)."""
        client = cls()
        for path in sorted(directory.glob("*.truth.json")):
            truth = json.loads(path.read_text(encoding="utf-8"))
            client.register(truth["header"], ColumnMapping.model_validate(truth["mapping"]))
        return client


class UnavailableLLMClient:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    def infer_schema(self, sample: MaskedSample) -> ColumnMapping:
        raise LLMError(self._reason)

    def categorize_merchants(
        self, merchants: Sequence[MaskedMerchant], categories: Sequence[str]
    ) -> dict[int, str]:
        raise LLMError(self._reason)


def build_llm_client(settings: Settings) -> LLMClient:
    """Pick the client implied by settings. Demo mode never makes network calls."""
    if settings.demo_mode or settings.llm_provider == "fake":
        return FakeLLMClient.from_samples_dir(settings.samples_dir)
    if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value():
        return UnavailableLLMClient(
            "ANTHROPIC_API_KEY is not set - map the columns manually or configure a key"
        )
    return AnthropicLLMClient(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.llm_model,
        effort=settings.llm_effort,
        timeout=settings.llm_timeout_seconds,
    )
