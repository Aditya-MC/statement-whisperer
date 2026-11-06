"""End-to-end import of one statement file.

    bytes -> detect type -> raw table -> header split -> mapping (LLM or user)
          -> normalize -> validate -> dedupe -> insert

The file's bytes live only in memory for the duration of this call. Nothing is written to disk
and nothing from the file is logged.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion import PARSER_VERSION
from app.ingestion.dedupe import chunked, file_sha256, transaction_hashes
from app.ingestion.detect import FileType, detect_file_type, ensure_supported
from app.ingestion.loaders import FileReadError, Table, load_raw_table, split_header
from app.ingestion.normalize import MappingError, normalize
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
        _run(db, llm, account, imp, data, file_type, mapping_override)
    except Exception:
        db.rollback()
        raise
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
) -> None:
    try:
        table = _prepare(data, file_type)
    except FileReadError as exc:
        imp.status = ImportStatus.failed
        imp.error_message = str(exc)
        db.flush()
        return

    imp.columns = [h[:_MAX_HEADER_LABEL] for h in table.header]

    if mapping_override is not None:
        mapping, imp.mapping_source = mapping_override, "user"
    else:
        try:
            mapping = llm.infer_schema(build_masked_sample(table.header, table.body))
            imp.mapping_source = "llm"
        except LLMError as exc:
            imp.status = ImportStatus.needs_review
            imp.mapping = None
            imp.error_message = f"Automatic column detection failed: {exc}"
            db.flush()
            return
    imp.mapping = mapping.model_dump(mode="json")

    try:
        result = normalize(table, mapping)
    except MappingError as exc:
        imp.status = ImportStatus.needs_review
        imp.error_message = str(exc)
        db.flush()
        return

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
    _apply_report(imp, report)

    if not report.ok:
        imp.status = ImportStatus.needs_review
        imp.error_message = "Validation failed - review the column mapping"
        db.flush()
        return

    chrono, _ = order_chronologically(result.transactions)
    hashes = transaction_hashes(account.id, chrono)
    existing_hashes: set[str] = set()
    for chunk in chunked(hashes):
        existing_hashes.update(
            db.scalars(select(Transaction.dedupe_hash).where(Transaction.dedupe_hash.in_(chunk)))
        )

    db.flush()  # assigns imp.id
    inserted = 0
    for idx, (txn, h) in enumerate(zip(chrono, hashes, strict=True)):
        if h in existing_hashes:
            continue
        db.add(
            Transaction(
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
        )
        inserted += 1

    imp.inserted_count = inserted
    imp.duplicate_count = len(hashes) - inserted
    imp.status = ImportStatus.completed
    imp.completed_at = utcnow()
    db.flush()


def _apply_report(imp: Import, report: ValidationReport) -> None:
    s = report.stats
    imp.validation = report.model_dump(mode="json")
    imp.row_count = s.transactions
    imp.date_from, imp.date_to = s.date_from, s.date_to
    imp.opening_balance, imp.closing_balance = s.opening_balance, s.closing_balance
