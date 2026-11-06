"""Run every synthetic statement through the full pipeline and compare with ground truth.

The LLM is replaced by a fake that returns each layout's known-correct mapping, so this suite
tests everything after schema inference: loading, header detection, masking, normalization,
validation, dedupe and storage. The pass rate is printed at the end of the pytest run.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.pipeline import ingest
from app.models import Account, ImportStatus, Transaction
from app.schemas.mapping import ColumnMapping
from app.services.llm import FakeLLMClient
from tests.conftest import SAMPLES_DIR, truth_files

TRUTH = truth_files()


def test_corpus_is_present() -> None:
    assert len(TRUTH) >= 12, "run `python samples/generate.py` to create the synthetic corpus"


@pytest.mark.parametrize("truth_path", TRUTH, ids=lambda p: p.name.removesuffix(".truth.json"))
def test_layout_matches_ground_truth(
    truth_path: Path, db: Session, corpus_results: list[tuple[str, bool]]
) -> None:
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    mapping = ColumnMapping.model_validate(truth["mapping"])
    llm = FakeLLMClient()
    llm.register(truth["header"], mapping)
    account = Account(bank_name="Synthetic", nickname=truth["layout"], currency=mapping.currency)
    db.add(account)
    db.commit()

    ok = False
    try:
        data = (SAMPLES_DIR / truth["file"]).read_bytes()
        imp = ingest(db, llm, account, data, truth["file"])
        assert imp.status == ImportStatus.completed, imp.validation or imp.error_message

        expected = truth["expected"]
        got = db.scalars(
            select(Transaction)
            .where(Transaction.import_id == imp.id)
            .order_by(Transaction.row_index)
        ).all()
        assert len(got) == expected["count"]
        for g, e in zip(got, expected["transactions"], strict=True):
            assert g.date.isoformat() == e["date"]
            assert g.amount == Decimal(e["amount"]), e["narration"]
            assert g.raw_narration == e["narration"]
            if e["balance"] is not None:
                assert g.balance == Decimal(e["balance"])
            assert g.currency == mapping.currency
        if expected["opening_balance"] is not None:
            assert imp.opening_balance == Decimal(expected["opening_balance"])
            assert imp.closing_balance == Decimal(expected["closing_balance"])

        # Privacy: no narration text reached the (fake) LLM.
        sent = " ".join(" ".join(row) for s in llm.calls for row in s.rows)
        for e in expected["transactions"]:
            assert e["narration"] not in sent
        ok = True
    finally:
        corpus_results.append((truth["layout"], ok))


def test_committed_samples_match_generator(generator, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """The committed corpus must be what the generator produces (it is deterministic)."""
    for layout in generator.LAYOUTS:
        generator.generate(layout, tmp_path)
        name = f"{layout.name}.truth.json"
        assert (tmp_path / name).read_text(encoding="utf-8") == (SAMPLES_DIR / name).read_text(
            encoding="utf-8"
        ), f"{name} is stale - rerun samples/generate.py"
        if layout.fmt != "xlsx":  # xlsx embeds a timestamp
            data = f"{layout.name}.{layout.extension}"
            assert (tmp_path / data).read_bytes() == (SAMPLES_DIR / data).read_bytes()
