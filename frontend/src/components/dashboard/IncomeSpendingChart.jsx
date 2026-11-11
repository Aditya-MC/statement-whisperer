import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCompact, toChartSeries } from "../../lib/dashboard.js";
import { formatMoney } from "../../lib/format.js";
import ChartCard, { LegendItem } from "./ChartCard.jsx";
import ChartTooltip from "./ChartTooltip.jsx";

const NAMES = { income: "Income", spending: "Spending" };
const AXIS_TICK = { fill: "var(--axis-text)", fontSize: 12 };

/** Income vs spending per week/month: two series, grouped columns, one shared y-axis. */
export default function IncomeSpendingChart({ series, currency, granularity }) {
  const data = toChartSeries(series);
  return (
    <ChartCard
      title="Income vs spending"
      subtitle={`Per ${granularity}. Transfers between your own accounts are excluded.`}
      legend={
        <div className="flex items-center gap-3">
          <LegendItem color="var(--series-1)">Income</LegendItem>
          <LegendItem color="var(--series-2)">Spending</LegendItem>
        </div>
      }
      renderChart={() => (
        <div className="h-64" role="img" aria-label="Income and spending per period; switch to Table for values">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barGap={3} barCategoryGap="35%">
              <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="3 5" />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={{ stroke: "var(--axis)" }}
                tick={AXIS_TICK}
                minTickGap={12}
              />
              <YAxis
                tickFormatter={(v) => formatCompact(v, currency)}
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                width={56}
              />
              <Tooltip
                cursor={{ fill: "var(--surface-2)", radius: 12 }}
                content={<ChartTooltip currency={currency} names={NAMES} />}
              />
              <Bar dataKey="income" fill="var(--series-1)" radius={[6, 6, 0, 0]} maxBarSize={18} isAnimationActive={false} />
              <Bar dataKey="spending" fill="var(--series-2)" radius={[6, 6, 0, 0]} maxBarSize={18} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      renderTable={() => (
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-sm">
            <thead className="eyebrow text-left">
              <tr className="border-b border-line">
                <th className="py-2 font-medium">Period</th>
                <th className="py-2 text-right font-medium">Income</th>
                <th className="py-2 text-right font-medium">Spending</th>
                <th className="py-2 text-right font-medium">Net</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {series.map((s) => (
                <tr key={s.start} className="border-b border-line last:border-0">
                  <td className="py-1.5">{s.label}</td>
                  <td className="py-1.5 text-right">{formatMoney(s.income, currency)}</td>
                  <td className="py-1.5 text-right">{formatMoney(s.spending, currency)}</td>
                  <td className="py-1.5 text-right">{formatMoney(Number(s.income) - Number(s.spending), currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    />
  );
}
