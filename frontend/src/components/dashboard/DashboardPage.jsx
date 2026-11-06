import { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api.js";
import { categoryLabels } from "../../lib/categories.js";
import { PRESETS, formatPercent, presetRange } from "../../lib/dashboard.js";
import { formatDate, formatMoney } from "../../lib/format.js";
import CategoryChart from "./CategoryChart.jsx";
import IncomeSpendingChart from "./IncomeSpendingChart.jsx";

function StatTile({ label, value, tone, hint }) {
  const color = tone === "good" ? "text-good" : tone === "critical" ? "text-critical" : "text-ink";
  return (
    <div className="flex flex-col gap-1">
      <span className="eyebrow">{label}</span>
      <span className={`text-2xl font-semibold tracking-tight ${color}`}>{value}</span>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}

function Filters({ preset, setPreset, custom, setCustom, accounts, accountId, setAccountId, currencies, currency, setCurrency }) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-sm">
        <span className="eyebrow">Period</span>
        <select className="input" value={preset} onChange={(e) => setPreset(e.target.value)}>
          {PRESETS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      {preset === "custom" && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            <span className="eyebrow">From</span>
            <input type="date" className="input" value={custom.date_from ?? ""} max={custom.date_to ?? undefined}
              onChange={(e) => setCustom((c) => ({ ...c, date_from: e.target.value || null }))} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="eyebrow">To</span>
            <input type="date" className="input" value={custom.date_to ?? ""} min={custom.date_from ?? undefined}
              onChange={(e) => setCustom((c) => ({ ...c, date_to: e.target.value || null }))} />
          </label>
        </>
      )}
      <label className="flex flex-col gap-1 text-sm">
        <span className="eyebrow">Account</span>
        <select className="input" value={accountId ?? ""} onChange={(e) => setAccountId(e.target.value === "" ? null : Number(e.target.value))}>
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nickname}
            </option>
          ))}
        </select>
      </label>
      {currencies.length > 1 && (
        <label className="flex flex-col gap-1 text-sm">
          <span className="eyebrow">Currency</span>
          <select className="input" value={currency ?? ""} onChange={(e) => setCurrency(e.target.value || null)}>
            {currencies.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}

function TopMerchants({ rows, currency, labels, onDrill }) {
  const max = Math.max(...rows.map((r) => Number(r.amount)), 1);
  return (
    <section className="card flex flex-col gap-4">
      <header>
        <h2 className="text-sm font-semibold">Top merchants</h2>
        <p className="mt-0.5 text-xs text-muted">By money out. Click a row to see its transactions.</p>
      </header>
      {rows.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted">No spending in this range.</p>
      ) : (
        <table className="w-full table-fixed text-sm">
          <colgroup>
            <col />
            <col className="w-24" />
            <col className="w-28" />
          </colgroup>
          <tbody>
            {rows.map((r) => (
              <tr key={r.merchant} onClick={() => onDrill({ q: r.merchant })} className="cursor-pointer border-b border-line last:border-0 hover:bg-surface-2">
                <td className="py-2 pr-3">
                  <div className="truncate font-medium">{r.merchant}</div>
                  <div className="truncate text-xs text-muted">
                    {labels.get(r.category_id) ?? "Uncategorized"} · {r.count}×
                  </div>
                </td>
                <td className="py-2 pr-3 align-middle">
                  {/* thin share bar: one series, slot-1 color, fully rounded, no text */}
                  <div className="h-1 rounded-full bg-surface-2">
                    <div className="h-1 rounded-full bg-series-1" style={{ width: `${(Number(r.amount) / max) * 100}%` }} />
                  </div>
                </td>
                <td className="py-2 text-right tabular-nums">{formatMoney(r.amount, currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Recurring({ rows, currency, labels }) {
  return (
    <section className="card flex flex-col gap-4">
      <header>
        <h2 className="text-sm font-semibold">Recurring payments</h2>
        <p className="mt-0.5 text-xs text-muted">
          Merchants paid weekly or monthly at a similar amount (3+ payments). Looks back up to 13 months.
        </p>
      </header>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">
          None detected yet. Recurring payments show up once a few months of statements are imported.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="eyebrow text-left">
              <tr className="border-b border-line">
                <th className="py-2 font-medium">Merchant</th>
                <th className="py-2 font-medium">Every</th>
                <th className="py-2 text-right font-medium">Typical</th>
                <th className="py-2 text-right font-medium">Per month</th>
                <th className="py-2 text-right font-medium">Next expected</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {rows.map((r) => (
                <tr key={r.merchant} className="border-b border-line last:border-0">
                  <td className="py-2">
                    <div className="font-medium">{r.merchant}</div>
                    <div className="text-xs text-muted">
                      {labels.get(r.category_id) ?? "Uncategorized"} · {r.occurrences} payments
                    </div>
                  </td>
                  <td className="py-2 text-ink-2">{r.cadence === "weekly" ? "Week" : "Month"}</td>
                  <td className="py-2 text-right">{formatMoney(r.typical_amount, currency)}</td>
                  <td className="py-2 text-right">{formatMoney(r.monthly_cost, currency)}</td>
                  <td className="py-2 text-right text-ink-2">{formatDate(r.next_expected)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function DashboardPage({ accounts, categories, onDrill, onImport, notify }) {
  const labels = useMemo(() => categoryLabels(categories), [categories]);
  const [preset, setPreset] = useState("all");
  const [custom, setCustom] = useState({ date_from: null, date_to: null });
  const [accountId, setAccountId] = useState(null);
  const [currency, setCurrency] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const range = preset === "custom" ? custom : presetRange(preset);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .dashboard({ ...range, account_id: accountId, currency })
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && notify(e.message, "error"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // `range` is derived from preset/custom, so its inputs are the dependencies.
  }, [preset, custom.date_from, custom.date_to, accountId, currency, notify]);

  if (accounts.length === 0) {
    return (
      <section className="card flex flex-col items-start gap-3">
        <h2 className="text-base font-semibold">Nothing to show yet</h2>
        <p className="text-sm text-ink-2">Import a bank statement and your dashboard appears here.</p>
        <button type="button" className="btn-primary" onClick={onImport}>
          Import a statement
        </button>
      </section>
    );
  }
  if (!data) return <p className="text-sm text-muted">Loading…</p>;

  const s = data.summary;
  const cur = data.currency ?? accounts[0]?.currency ?? "INR";
  const net = Number(s.net);
  const period = data.period.date_from
    ? `${formatDate(data.period.date_from)} – ${formatDate(data.period.date_to)}`
    : "No transactions yet";
  const drill = (extra) => onDrill({ ...extra, account_id: accountId, date_from: data.period.date_from, date_to: data.period.date_to });

  return (
    <div className="flex flex-col gap-6">
      <Filters
        preset={preset} setPreset={setPreset} custom={custom} setCustom={setCustom}
        accounts={accounts} accountId={accountId} setAccountId={setAccountId}
        currencies={data.currencies} currency={data.currency} setCurrency={setCurrency}
      />

      {/* Refetch keeps the frame: previous numbers stay, dimmed, until new ones arrive. */}
      <div className={`flex flex-col gap-6 transition-opacity ${loading ? "opacity-50" : ""}`} aria-busy={loading}>
        <section className="card grid gap-6 md:grid-cols-[1.4fr_1fr_1fr_1fr] md:items-end">
          <div className="flex flex-col gap-1">
            <span className="eyebrow">Spent</span>
            <span className="text-5xl font-semibold tracking-tight">{formatMoney(s.spending, cur)}</span>
            <span className="text-xs text-muted">
              {period} · {s.transactions} transactions
            </span>
          </div>
          <StatTile label="Income" value={formatMoney(s.income, cur)} hint={Number(s.refunds) > 0 ? `+ ${formatMoney(s.refunds, cur)} refunds` : undefined} />
          <StatTile label="Net saved" value={formatMoney(s.net, cur)} tone={net > 0 ? "good" : net < 0 ? "critical" : undefined} hint={net < 0 ? "Spent more than earned" : undefined} />
          <StatTile label="Savings rate" value={formatPercent(s.savings_rate)} hint={s.savings_rate === null ? "No income in this range" : "Net ÷ income"} />
        </section>

        {(s.uncategorized_count > 0 || s.excluded_transfers > 0) && (
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-ink-2">
            {s.uncategorized_count > 0 && (
              <button type="button" className="underline-offset-2 hover:underline" onClick={() => drill({ uncategorized: true })}>
                {formatMoney(s.uncategorized_spend, cur)} across {s.uncategorized_count} uncategorized transactions. Review →
              </button>
            )}
            {s.excluded_transfers > 0 && <span>{s.excluded_transfers} transfers between your own accounts left out.</span>}
          </div>
        )}

        <IncomeSpendingChart series={data.series} currency={cur} granularity={data.period.granularity} />

        <div className="grid gap-6 lg:grid-cols-2">
          <CategoryChart rows={data.by_category} refunds={s.refunds} currency={cur} onDrill={drill} />
          <TopMerchants rows={data.top_merchants} currency={cur} labels={labels} onDrill={drill} />
        </div>

        <Recurring rows={data.recurring} currency={cur} labels={labels} />
      </div>
    </div>
  );
}
