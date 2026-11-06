"""End-to-end import of one statement file.

    bytes -> detect type -> raw table -> header split -> mapping (user, saved, or LLM)
          -> normalize -> validate -> dedupe -> insert -> categorize -> link transfers

The file's bytes live only in memory for the duration of this call. Nothing is written to disk
and nothing from the file is logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorization.categorizer import categorize_transactions
from app.categorization.transfers import link_transfers
from app.ingestion import PARSER_VERSION
from app.ingestion.dedupe import chunked, file_sha256, transaction_hashes
from app.ingestion.detect import FileType, detect_file_type, ensure_supported
from app.ingestion.loaders import FileReadError, Table, load_raw_table, split_header
from app.ingestion.normalize import MappingError, NormalizeResult, normalize
from app.ingestion.validate import order_chronologically, validate
from app.models import Account, Import, ImportStatus, Transaction, TxnType
from app.models._types import utcnow
from app.schemas.mapping import ColumnMapping
from app.schemas.report import Issue, ValidationReport
from app.services.llm import LLMClient, LLMError
from app.services.masking import build_masked_sample

log = logging.getLogger(__name__)

_MAX_HEADER_LABEL = 60


class DuplicateFileError(Exception):
    def __init__(self, existing_import_id: int) -> None:
        super().__init__("This file was already imported into this account")
        self.existing_import_id = existing_import_id


class FileMismatchError(ValueError):
    """A retry was attempted with a different file than the original import."""


def _prepare(data: bytes, file_type: FileType) -> Table:
    return split_header(load_raw_table(data, file_type))


def find_completed_duplicate(db: Session, account_id: int, file_hash: str) -> Import | None:
    return db.scalar(
        select(Import).where(
            Import.account_id == account_id,
            Import.file_hash == file_hash,
            Import.status == ImportStatus.completed,
        )
    )


def ingest(
    db: Session,
    llm: LLMClient,
    account: Account,
    data: bytes,
    filename: str | None,
    *,
    mapping_override: ColumnMapping | None = None,
    existing: Import | None = None,
) -> Import:
    """Import a statement and return the `Import` row (committed).

    Raises `UnsupportedFileError` before creating any record for file types we can't handle,
    and `DuplicateFileError` if the same file was already imported into this account.
    When `existing` is given (a retry), the file must hash to the same value.
    """
    file_hash = file_sha256(data)
    if existing is not None and existing.file_hash != file_hash:
        raise FileMismatchError("The uploaded file differs from the original import")
    dup = find_completed_duplicate(db, account.id, file_hash)
    if dup is not None:
        raise DuplicateFileError(dup.id)

    file_type = detect_file_type(filename, data)
    ensure_supported(file_type)

    imp = existing or Import(account_id=account.id, file_hash=file_hash)
    imp.file_type = file_type.value
    imp.parser_version = PARSER_VERSION
    imp.status = ImportStatus.failed
    imp.error_message = None
    imp.validation = None
    if existing is None:
        db.add(imp)

    try:
        new_rows = _run(db, llm, account, imp, data, file_type, mapping_override)
    except Exception:
        db.rollback()
        raise
    if new_rows:
        _categorize_new(db, llm, new_rows)
    db.commit()
    log.info(
        "import id=%s status=%s rows=%s inserted=%s duplicates=%s",
        imp.id, imp.status, imp.row_count, imp.inserted_count, imp.duplicate_count,
    )  # fmt: skip
    return imp


def _run(
    db: Session,
    llm: LLMClient,
    account: Account,
    imp: Import,
    data: bytes,
    file_type: FileType,
    mapping_override: ColumnMapping | None,
) -> list[Transaction]:
    """Run the import; returns the newly inserted transactions (empty unless completed)."""
    try:
        table = _prepare(data, file_type)
    except FileReadError as exc:
        imp.status = ImportStatus.failed
        imp.error_message = str(exc)
        db.flush()
        return []

    imp.columns = [h[:_MAX_HEADER_LABEL] for h in table.header]

    # Mapping sources, in order: the user's, a saved one that worked for this layout before
    # (free, offline), then the LLM as a last resort.
    attempt: _Attempt | None = None
    if mapping_override is not None:
        attempt = _evaluate(table, mapping_override, "user", account)
    else:
        saved = find_saved_mapping(db, account.id, imp.columns)
        if saved is not None:
            attempt = _evaluate(table, saved, "saved", account)
        if attempt is None or not attempt.ok:
            try:
                inferred = llm.infer_schema(build_masked_sample(table.header, table.body))
                attempt = _evaluate(table, inferred, "llm", account)
            except LLMError as exc:
                if attempt is None:
                    imp.status = ImportStatus.needs_review
                    imp.mapping = None
                    imp.error_message = f"Automatic column detection failed: {exc}"
                    db.flush()
                    return []
                # Keep the saved mapping so the review screen starts from it.

    assert attempt is not None
    mapping = attempt.mapping
    imp.mapping = mapping.model_dump(mode="json")
    imp.mapping_source = attempt.source
    if attempt.error is not None:
        imp.status = ImportStatus.needs_review
        imp.error_message = attempt.error
        db.flush()
        return []
    assert attempt.result is not None and attempt.report is not None
    result, report = attempt.result, attempt.report
    _apply_report(imp, report)

    if not report.ok:
        imp.status = ImportStatus.needs_review
        imp.error_message = (
            "The saved layout for these columns didn't fit this file - review the mapping"
            if attempt.source == "saved"
            else "Validation failed - review the column mapping"
        )
        db.flush()
        return []

    chrono, _ = order_chronologically(result.transactions)
    hashes = transaction_hashes(account.id, chrono)
    existing_hashes: set[str] = set()
    for chunk in chunked(hashes):
        existing_hashes.update(
            db.scalars(select(Transaction.dedupe_hash).where(Transaction.dedupe_hash.in_(chunk)))
        )

    db.flush()  # assigns imp.id
    new_rows: list[Transaction] = []
    for idx, (txn, h) in enumerate(zip(chrono, hashes, strict=True)):
        if h in existing_hashes:
            continue
        row = Transaction(
            account_id=account.id,
            import_id=imp.id,
            date=txn.date,
            amount=txn.amount,
            type=TxnType.debit if txn.amount < 0 else TxnType.credit,
            balance=txn.balance,
            currency=mapping.currency,
            raw_narration=txn.raw_narration,
            row_index=idx,
            dedupe_hash=h,
        )
        db.add(row)
        new_rows.append(row)

    imp.inserted_count = len(new_rows)
    imp.duplicate_count = len(hashes) - len(new_rows)
    imp.status = ImportStatus.completed
    imp.completed_at = utcnow()
    db.flush()
    return new_rows


@dataclass
class _Attempt:
    """One mapping applied to the table: either a validation report or a mapping error."""

    mapping: ColumnMapping
    source: str  # "user" | "saved" | "llm"
    result: NormalizeResult | None = None
    report: ValidationReport | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.report is not None and self.report.ok


def _evaluate(table: Table, mapping: ColumnMapping, source: str, account: Account) -> _Attempt:
    try:
        result = normalize(table, mapping)
    except MappingError as exc:
        return _Attempt(mapping, source, error=str(exc))
    report = validate(result)
    if mapping.currency != account.currency:
        report.warnings.append(
            Issue(
                severity="warning",
                code="currency_mismatch",
                message=f"Statement currency {mapping.currency} differs from account currency "
                f"{account.currency}",
            )
        )
    return _Attempt(mapping, source, result=result, report=report)


def _header_key(columns: list[str] | None) -> tuple[str, ...]:
    return tuple(" ".join(c.lower().split()) for c in (columns or []))


#: How many past completed imports to search for a reusable mapping.
_SAVED_MAPPING_SCAN = 200


def find_saved_mapping(db: Session, account_id: int, columns: list[str]) -> ColumnMapping | None:
    """Mapping from the most recent completed import with the same column headers.

    Prefers the same account. Lets a bank's layout be mapped once (by the user or the LLM)
    and reused for every later statement with no LLM call. Validation still checks every
    import, so a layout that changed only subtly can't slip through.
    """
    key = _header_key(columns)
    if not key:
        return None
    rows = db.execute(
        select(Import.account_id, Import.columns, Import.mapping)
        .where(Import.status == ImportStatus.completed, Import.mapping.is_not(None))
        .order_by(Import.id.desc())
        .limit(_SAVED_MAPPING_SCAN)
    ).all()
    matches = [r for r in rows if _header_key(r.columns) == key]
    if not matches:
        return None
    best = next((r for r in matches if r.account_id == account_id), matches[0])
    try:
        return ColumnMapping.model_validate(best.mapping)
    except ValueError:
        return None


def _categorize_new(db: Session, llm: LLMClient, rows: list[Transaction]) -> None:
    """Categorize freshly imported rows and link transfers.

    Runs in a savepoint: if anything here fails, the validated import is still kept and its
    transactions simply stay uncategorized (POST /api/categorize can retry later).
    """
    try:
        with db.begin_nested():
            result = categorize_transactions(db, llm, rows)
            pairs = link_transfers(db)
        log.info(
            "categorized rows=%s sources=%s llm_merchants=%s uncategorized=%s transfers=%s",
            result.processed, dict(result.by_source), result.llm_merchants,
            result.uncategorized, pairs,
        )  # fmt: skip
    except Exception:
        log.exception("categorization failed; import kept uncategorized")


def _apply_report(imp: Import, report: ValidationReport) -> None:
    s = report.stats
    imp.validation = report.model_dump(mode="json")
    imp.row_count = s.transactions
    imp.date_from, imp.date_to = s.date_from, s.date_to
    imp.opening_balance, imp.closing_balance = s.opening_balance, s.closing_balance
