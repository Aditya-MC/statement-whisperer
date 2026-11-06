import { formatDate, formatMoney } from "../lib/format.js";
import { StatusPill } from "./ui.jsx";

const MAPPING_SOURCE_TEXT = {
  llm: "layout detected by AI",
  user: "layout set by you",
  saved: "reused the saved layout for these columns",
};

function Stat({ label, value }) {
  return (
    <div>
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="font-medium tabular-nums">{value ?? "—"}</dd>
    </div>
  );
}

function IssueList({ title, issues, counts, tone }) {
  if (!issues?.length) return null;
  const color = tone === "error" ? "text-red-700 dark:text-red-300" : "text-amber-700 dark:text-amber-300";
  return (
    <div className="mt-4">
      <h3 className={`mb-1 text-sm font-semibold ${color}`}>{title}</h3>
      <ul className="max-h-56 overflow-auto rounded border border-zinc-200 text-sm dark:border-zinc-800">
        {issues.map((i, idx) => (
          <li key={idx} className="flex gap-3 border-b border-zinc-100 px-3 py-1.5 last:border-0 dark:border-zinc-800">
            <span className="w-16 shrink-0 text-zinc-500 tabular-nums">{i.row ? `row ${i.row}` : ""}</span>
            <span>
              {i.message}
              {i.column ? <span className="text-zinc-500"> · {i.column}</span> : null}
            </span>
          </li>
        ))}
      </ul>
      {Object.entries(counts ?? {}).some(([code, n]) => n > issues.filter((i) => i.code === code).length) && (
        <p className="mt-1 text-xs text-zinc-500">Showing the first issues of each kind only.</p>
      )}
    </div>
  );
}

export default function ImportResult({ imp, onViewTransactions }) {
  const v = imp.validation;
  const s = v?.stats;
  const currency = imp.mapping?.currency;
  return (
    <section className="card" aria-live="polite">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold">Import #{imp.id}</h2>
        <StatusPill status={imp.status} />
        {imp.mapping_source && <span className="text-xs text-zinc-500">{MAPPING_SOURCE_TEXT[imp.mapping_source] ?? ""}</span>}
        {imp.status === "completed" && (
          <button type="button" className="btn-ghost ml-auto" onClick={onViewTransactions}>
            View transactions →
          </button>
        )}
      </div>
      {imp.error_message && <p className="mb-3 text-sm text-zinc-700 dark:text-zinc-300">{imp.error_message}</p>}
      {s && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Transactions" value={s.transactions} />
          <Stat label="New / duplicates" value={imp.status === "completed" ? `${imp.inserted_count} / ${imp.duplicate_count}` : null} />
          <Stat label="Period" value={s.date_from ? `${formatDate(s.date_from)} – ${formatDate(s.date_to)}` : null} />
          <Stat label="Order" value={s.order} />
          <Stat label="Opening balance" value={s.opening_balance != null ? formatMoney(s.opening_balance, currency) : null} />
          <Stat label="Closing balance" value={s.closing_balance != null ? formatMoney(s.closing_balance, currency) : null} />
          <Stat label="Money in" value={formatMoney(s.total_credits, currency)} />
          <Stat label="Money out" value={formatMoney(s.total_debits, currency)} />
        </dl>
      )}
      <IssueList title="Problems" issues={v?.errors} counts={v?.issue_counts} tone="error" />
      <IssueList title="Warnings" issues={v?.warnings} counts={v?.issue_counts} tone="warning" />
    </section>
  );
}
