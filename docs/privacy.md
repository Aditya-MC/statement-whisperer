# Privacy

This app handles bank statements, so it is built to keep as little as possible and send even less.

## What is sent to the LLM

**Phase 1 (schema inference): one request per new statement layout**, containing:

- The table's **header labels**, with any long digit runs masked (`Acct 1234567` becomes `Acct <num>`).
- **Up to 10 data rows**, masked cell by cell:

| Cell looks like | Sent as | Example |
|---|---|---|
| A date | as-is | `05/01/2024` |
| An amount (up to 14 digits) | as-is | `-1,234.56`, `1.234,56`, `1,200.00 Dr` |
| A short debit/credit word | as-is | `DR`, `Credit` |
| A 3-letter currency code | as-is | `AUD` |
| A bare number of 7+ digits | `<digits:N>` | account, card, cheque or reference numbers |
| Anything else (narrations, names, addresses) | `<text:N>` | `UPI/4123.../JANE DOE` becomes `<text:29>` |

Preamble lines above the header (bank name, account holder, account number, address) are never sent. Neither are rows beyond the sample or file names.

**Phase 2 (categorization, planned):** only cleaned merchant strings, such as `SWIGGY` or `AMAZON MKTPLACE`, after `mask_free_text` has removed emails, UPI handles, phone/card/account numbers and other long digit runs. Each merchant is sent once and the result is cached.

The masking code is in `backend/app/services/masking.py`. The LLM gateway accepts only a `MaskedSample` (`backend/app/services/llm.py`), and `tests/test_synthetic_corpus.py` checks for every sample layout that no narration text reaches the LLM.

With no API key configured, or in demo mode, nothing is sent anywhere. Imports land in `needs_review` and you map the columns yourself.

## What is stored

| Stored | Not stored |
|---|---|
| Normalized transactions, including the original narration text | The uploaded file (processed in memory; Starlette's temp spool is closed right after reading) |
| SHA-256 hash of each uploaded file (for duplicate detection) | File names |
| The column mapping and the statement's header labels | Full account numbers (only `last4`, enforced by a DB constraint and API validation) |
| A validation report (row numbers and messages, no cell values) | PDF passwords (Phase 4: used in memory only) |

## What is logged

Only import metadata: id, status and counts. No narrations, amounts or file contents. The SQLAlchemy engine runs with `hide_parameters=True`, so SQL logs and database error messages don't contain values even at DEBUG level. Parser exceptions are replaced by generic messages. `tests/api/test_api.py::test_no_statement_content_in_logs` enforces this.

## Repository hygiene

`.gitignore` excludes `.env`, `*.db`, `uploads/`, `backups/` and `samples/real/`. Keep any real statements in `samples/real/` if you need them locally. Everything under `samples/synthetic/` is generated fake data.
