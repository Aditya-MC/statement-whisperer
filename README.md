# Bank Statement Analyzer

A personal-finance ledger that works with statements from any bank. Upload a CSV or XLSX statement (PDF support comes later). The app works out the layout at runtime, normalizes every transaction into one schema, checks the result against the statement's balances, and stores it permanently.

> Status: **Phase 1 (ingestion) in progress.** See [docs/architecture.md](docs/architecture.md).

## Repository layout

```
backend/    FastAPI + SQLAlchemy + Alembic (Python 3.11+)
frontend/   React + Vite + Tailwind (Phase 2)
docs/       Architecture and privacy notes
samples/    Synthetic statement generator and generated fixtures (never real data)
scripts/    dev.ps1 task runner
```

## Quick start (Windows / PowerShell)

```powershell
copy .env.example .env          # then set ANTHROPIC_API_KEY
.\scripts\dev.ps1 setup         # creates backend\.venv and installs deps locally
.\scripts\dev.ps1 migrate       # creates the SQLite database
.\scripts\dev.ps1 test          # runs the test suite
.\scripts\dev.ps1 run           # API at http://127.0.0.1:8000/docs
```
