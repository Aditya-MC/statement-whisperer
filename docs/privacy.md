# Privacy

This app handles bank statements, so it is built to keep as little as possible and send even less.

## What is sent to the LLM

**Phase 1 (schema inference): at most one request per new statement layout.** A layout that has imported successfully once is reused from the database, so later statements with the same columns send nothing. Each request contains:

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

**Phase 2 (categorization): only for merchants no rule or cache entry covers**, one batched request per import, containing for each unique merchant:

- the **cleaned merchant name** (e.g. `SWIGGY`, `CITY POWER UTILITY`). `mask_free_text` then removes any remaining emails, UPI handles and phone/card/account numbers;
- the direction (`debit` / `credit`);
- hint keywords from a fixed list (`SALARY`, `REFUND`, `EMI`…);
- the category list (built-in categories plus any you've added, so don't put anything private in a category name).

Not sent: raw narrations, amounts, dates, balances, account details, or **person names**. Person-to-person payments (IMPS/NEFT/UPI/cheque to something that looks like a name) are flagged during merchant cleanup, categorized locally as *Transfer to Others*, and never sent. The detection is a heuristic that errs toward treating names as people, which costs some accuracy in exchange for privacy. For example, in UPI narrations a payee that is a raw handle (`…@pty`), a phone number, or a lone word with no business signal counts as a person. A correction fixes it for good. Each merchant is sent at most once, and the answer is cached as a rule.

The masking code is in `backend/app/services/masking.py`. The LLM gateway accepts only `MaskedSample` / `MaskedMerchant` inputs (`backend/app/services/llm.py`). Tests check that no narration text reaches the LLM for any sample layout (`tests/test_synthetic_corpus.py`) and that person names and rule-covered merchants are never sent (`tests/test_categorizer.py`).

With no API key configured, or in demo mode, nothing is sent anywhere. Imports land in `needs_review` where you map the columns yourself, and categorization uses rules and built-in hints only.

## What is stored

| Stored | Not stored |
|---|---|
| Normalized transactions, including the original narration text | The uploaded file (processed in memory; Starlette's temp spool is closed right after reading) |
| SHA-256 hash of each uploaded file (for duplicate detection) | File names |
| The column mapping and the statement's header labels | Full account numbers (only `last4`, enforced by a DB constraint and API validation) |
| A validation report (row numbers and messages, no cell values) | PDF passwords (Phase 4: used in memory only) |
| Merchant rules (your corrections, which may include a payee's name, stay private to you) | Plain-text passwords (argon2id hashes only) |
| Your email and a hash of each session token | Raw session tokens (only your browser holds them) |

## Multiple users (shared server)

Each user's data is isolated by the application. Every query is filtered by the signed-in user, someone else's ids return "not found", and `tests/api/test_isolation.py` plus a live end-to-end check enforce this. Shared between users are only things that contain no personal data:
- built-in categories and brand rules;
- the column *structure* of a bank's statement layout (column positions, date and number format), so one tester mapping an IOB statement helps the next. No header labels or values from another user's file are ever shown.

**Be honest with testers:** whoever runs the server (the admin) and the hosting/database provider can technically read the database, as with any web app. The app gives the admin no screen for viewing other people's data, but it is not end-to-end encrypted. Testers should know this before uploading real statements, or test with a sample statement first. **Delete account** removes a user's data from the live database.

## What is logged

Only import and categorization metadata: ids, statuses and counts. No narrations, merchant names, amounts or file contents. The SQLAlchemy engine runs with `hide_parameters=True`, so SQL logs and database error messages don't contain values even at DEBUG level. Parser exceptions are replaced by generic messages. `tests/api/test_api.py::test_no_statement_content_in_logs` enforces this.

## Repository hygiene

`.gitignore` excludes `.env`, `*.db`, `uploads/`, `backups/` and `samples/real/`. Keep any real statements in `samples/real/` if you need them locally. Everything under `samples/synthetic/` is generated fake data.
