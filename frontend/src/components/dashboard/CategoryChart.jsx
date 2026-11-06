import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCompact, formatPercent } from "../../lib/dashboard.js";
import { formatMoney } from "../../lib/format.js";
import ChartCard from "./ChartCard.jsx";
import ChartTooltip from "./ChartTooltip.jsx";

const ROW = 34;

/**
 * Spending by category group: one series, so one color (slot 1) for every bar, ranked.
 * "Uncategorized" and the folded "Other" bar are de-emphasized in gray. Click a bar to open
 * those transactions.
 */
export default function CategoryChart({ rows, refunds, currency, onDrill }) {
  const data = rows.map((r) => ({ ...r, value: Number(r.amount) }));
  const drillable = (r) => !r.is_other;
  const open = (r) => drillable(r) && onDrill(r.category_id === null ? { uncategorized: true } : { category_id: r.category_id });

  return (
    <ChartCard
      title="Spending by category"
      subtitle="Click a bar to see its transactions."
      renderChart={() =>
        data.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted">No spending in this range.</p>
        ) : (
          <div style={{ height: data.length * ROW + 8 }} role="img" aria-label="Spending by category; switch to Table for values">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ top: 0, right: 64, bottom: 0, left: 0 }} barCategoryGap={10}>
                <XAxis type="number" hide domain={[0, "dataMax"]} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={118}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: "var(--ink-2)", fontSize: 12 }}
                />
                <Tooltip
                  cursor={{ fill: "var(--surface-2)" }}
                  content={<ChartTooltip currency={currency} names={{ value: "Spent" }} />}
                />
                <Bar
                  dataKey="value"
                  radius={[0, 4, 4, 0]}
                  maxBarSize={18}
                  isAnimationActive={false}
                  onClick={(d) => open(d.payload ?? d)}
                >
                  {data.map((r) => (
                    <Cell
                      key={r.name}
                      fill={r.category_id === null ? "var(--series-muted)" : "var(--series-1)"}
                      cursor={drillable(r) ? "pointer" : "default"}
                    />
                  ))}
                  <LabelList
                    dataKey="value"
                    position="right"
                    formatter={(v) => formatCompact(v, currency)}
                    style={{ fill: "var(--ink-2)", fontSize: 12 }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )
      }
      renderTable={() => (
        <table className="w-full text-sm">
          <thead className="eyebrow text-left">
            <tr className="border-b border-line">
              <th className="py-2 font-medium">Category</th>
              <th className="py-2 text-right font-medium">Txns</th>
              <th className="py-2 text-right font-medium">Share</th>
              <th className="py-2 text-right font-medium">Spent</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {rows.map((r) => (
              <tr
                key={r.name}
                onClick={() => open(r)}
                className={`border-b border-line last:border-0 ${drillable(r) ? "cursor-pointer hover:bg-surface-2" : ""}`}
              >
                <td className="py-1.5">{r.name}</td>
                <td className="py-1.5 text-right text-muted">{r.count}</td>
                <td className="py-1.5 text-right text-muted">{formatPercent(r.share)}</td>
                <td className="py-1.5 text-right">{formatMoney(r.amount, currency)}</td>
              </tr>
            ))}
            {Number(refunds) > 0 && (
              <tr className="text-muted">
                <td className="py-1.5" colSpan={3}>
                  Refunds credited back
                </td>
                <td className="py-1.5 text-right">−{formatMoney(refunds, currency)}</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    />
  );
}
