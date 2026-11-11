import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { formatPercent, sliceColor } from "../../lib/dashboard.js";
import { formatMoney } from "../../lib/format.js";
import ChartCard from "./ChartCard.jsx";

function PieTooltip({ active, payload, currency }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="pop-in border-2 border-(--glass-border) bg-surface-solid px-3.5 py-2.5 text-xs">
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="h-0.5 w-3 rounded-full" style={{ background: sliceColor(d.slot) }} />
        <span className="font-semibold tabular-nums text-ink">{formatMoney(d.amount, currency)}</span>
        <span className="text-muted">
          {d.name} · {formatPercent(d.share)}
        </span>
      </div>
    </div>
  );
}

/**
 * Share of spending by category group: at most 6 parts (top 5 groups + gray "Other") so the
 * whole stays readable at a glance. Slices are separated by a 2px surface-colored gap. The
 * legend is always visible with each part's share and amount (three light-mode slots are
 * below 3:1 contrast, so values never depend on color alone). Click a slice to drill in.
 */
export default function CategoryPie({ slices, total, currency, onDrill }) {
  const data = slices.map((s) => ({ ...s, value: Number(s.amount) }));
  const open = (s) => s.category_id !== null && onDrill({ category_id: s.category_id });

  const legend = (
    <ul className="flex min-w-0 flex-1 flex-col gap-2 text-sm">
      {data.map((s) => (
        <li key={s.name}>
          <button
            type="button"
            disabled={s.category_id === null}
            onClick={() => open(s)}
            className="flex w-full items-center gap-2 rounded-xl px-2 py-1 text-left enabled:hover:bg-surface-2 disabled:cursor-default"
          >
            <span aria-hidden="true" className="size-2.5 shrink-0 rounded-[2px]" style={{ background: sliceColor(s.slot) }} />
            <span className="truncate text-ink-2">{s.name}</span>
            <span className="ml-auto tabular-nums text-muted">{formatPercent(s.share)}</span>
            <span className="w-24 text-right tabular-nums">{formatMoney(s.amount, currency)}</span>
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <ChartCard
      title="Where the money went"
      subtitle="Share of money out by category group (before refunds). Each category keeps its color across filters."
      renderChart={() =>
        data.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted">No spending in this range.</p>
        ) : (
          <div className="flex flex-col items-center gap-6 sm:flex-row">
            <div className="relative size-48 shrink-0" role="img" aria-label="Spending share by category; the legend lists every value">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    dataKey="value"
                    nameKey="name"
                    innerRadius="62%"
                    outerRadius="100%"
                    startAngle={90}
                    endAngle={-270}
                    stroke="var(--surface-solid)"
                    strokeWidth={2}
                    isAnimationActive={false}
                    onClick={(d) => open(d.payload ?? d)}
                  >
                    {data.map((s) => (
                      <Cell key={s.name} fill={sliceColor(s.slot)} cursor={s.category_id !== null ? "pointer" : "default"} />
                    ))}
                  </Pie>
                  <Tooltip content={<PieTooltip currency={currency} />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="eyebrow">Money out</span>
                <span className="text-sm font-semibold">{formatMoney(total, currency)}</span>
              </div>
            </div>
            {legend}
          </div>
        )
      }
      renderTable={() => (
        <table className="w-full text-sm">
          <thead className="eyebrow text-left">
            <tr className="border-b border-line">
              <th className="py-2 font-medium">Group</th>
              <th className="py-2 text-right font-medium">Share</th>
              <th className="py-2 text-right font-medium">Spent</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {slices.map((s) => (
              <tr key={s.name} className="border-b border-line last:border-0">
                <td className="py-1.5">{s.name}</td>
                <td className="py-1.5 text-right text-muted">{formatPercent(s.share)}</td>
                <td className="py-1.5 text-right">{formatMoney(s.amount, currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    />
  );
}
