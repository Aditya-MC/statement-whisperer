import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../lib/api.js";
import { formatDate } from "../lib/format.js";
import AccountForm from "./AccountForm.jsx";
import ImportResult from "./ImportResult.jsx";
import MappingReview from "./MappingReview.jsx";
import { StatusPill } from "./ui.jsx";

export default function ImportPage({ accounts, accountId, setAccountId, onAccountCreated, onViewTransactions, notify }) {
  const [showNewAccount, setShowNewAccount] = useState(false);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  // The File object behind `result` (null for imports picked from history: the user re-selects it).
  const [resultFile, setResultFile] = useState(null);
  const [history, setHistory] = useState([]);

  const account = accounts.find((a) => a.id === accountId);

  const loadHistory = useCallback(() => {
    if (accountId == null) return setHistory([]);
    api.listImports(accountId).then(setHistory).catch(() => setHistory([]));
  }, [accountId]);

  useEffect(loadHistory, [loadHistory]);

  async function upload(e) {
    e.preventDefault();
    if (!file || accountId == null) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const imp = await api.uploadStatement({ accountId, file });
      setResult(imp);
      setResultFile(file);
      if (imp.status === "completed") notify(`Imported ${imp.inserted_count} transactions`, "success");
      loadHistory();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(`This file was already imported into this account (import #${err.body.existing_import_id}).`);
      } else {
        setError(err.message);
      }
    } finally {
      setBusy(false);
    }
  }

  function onResolved(imp) {
    setResult(imp);
    loadHistory();
    if (imp.status === "completed") notify(`Imported ${imp.inserted_count} transactions`, "success");
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
      <div className="flex flex-col gap-6">
        <section className="card">
          <h2 className="mb-4 text-[17px] font-semibold tracking-tight">Upload a statement</h2>
          {accounts.length === 0 || showNewAccount ? (
            <div className="mb-4">
              <p className="mb-3 text-sm text-ink-2">
                {accounts.length === 0 ? "Create an account to import into." : "New account"}
              </p>
              <AccountForm
                onCreated={(a) => {
                  setShowNewAccount(false);
                  onAccountCreated(a.id);
                }}
                onCancel={accounts.length ? () => setShowNewAccount(false) : undefined}
              />
            </div>
          ) : null}

          {accounts.length > 0 && (
            <form onSubmit={upload} className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">Account</span>
                <select
                  className="input min-w-48"
                  value={accountId ?? ""}
                  onChange={(e) => setAccountId(Number(e.target.value))}
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.nickname} · {a.bank_name}
                      {a.last4 ? ` ·· ${a.last4}` : ""} ({a.currency})
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">Statement file</span>
                <input
                  type="file"
                  accept=".csv,.tsv,.txt,.xlsx"
                  className="input file:mr-3 file:rounded-full file:border-0 file:bg-surface-2 file:px-3 file:py-1 file:text-ink"
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null);
                    setResult(null);
                    setError(null);
                  }}
                />
              </label>
              <button className="btn-primary" disabled={!file || busy}>
                {busy ? "Importing…" : "Import"}
              </button>
              {!showNewAccount && (
                <button type="button" className="btn-ghost" onClick={() => setShowNewAccount(true)}>
                  + Account
                </button>
              )}
            </form>
          )}
          <p className="mt-3 text-xs text-muted">
            CSV, TSV or XLSX from any bank. The file is processed in memory and never stored. Only the
            header and up to 10 masked rows are used to detect the layout.
          </p>
          {error && <p className="mt-3 text-sm text-critical">{error}</p>}
        </section>

        {result && <ImportResult imp={result} onViewTransactions={onViewTransactions} />}
        {result?.status === "needs_review" && (
          <MappingReview key={result.id} imp={result} file={resultFile} accountCurrency={account?.currency} onResolved={onResolved} />
        )}
      </div>

      <aside className="card h-fit">
        <h2 className="mb-4 text-[17px] font-semibold tracking-tight">Recent imports</h2>
        {history.length === 0 ? (
          <p className="text-sm text-muted">None yet.</p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {history.slice(0, 12).map((h) => (
              <li key={h.id}>
                <button
                  type="button"
                  onClick={() => {
                    setResult(h);
                    setResultFile(null);
                  }}
                  className="flex w-full items-center justify-between gap-2 rounded-xl px-2 py-1 text-left hover:bg-surface-2"
                >
                  <span className="truncate">
                    #{h.id} {h.date_from ? `${formatDate(h.date_from)} – ${formatDate(h.date_to)}` : h.file_type}
                  </span>
                  <StatusPill status={h.status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
