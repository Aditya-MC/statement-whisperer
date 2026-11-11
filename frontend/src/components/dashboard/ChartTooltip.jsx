import { formatMoney } from "../../lib/format.js";

/**
 * Recharts tooltip body. Values lead (strong), series names follow (muted); rows are keyed by
 * a short stroke of the series color rather than a filled box.
 */
export default function ChartTooltip({ active, payload, label, currency, names = {} }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-36 rounded-2xl border border-line bg-surface px-3.5 py-2.5 text-xs shadow-soft">
      {label && <div className="mb-1.5 font-medium text-ink-2">{label}</div>}
      <ul className="flex flex-col gap-1">
        {payload.map((p) => (
          <li key={p.dataKey} className="flex items-center gap-2">
            <span aria-hidden="true" className="h-0.5 w-3 rounded-full" style={{ background: p.color ?? p.fill }} />
            <span className="font-semibold tabular-nums text-ink">{formatMoney(p.value, currency)}</span>
            <span className="text-muted">{names[p.dataKey] ?? p.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
