import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCompact, toChartSeries } from "../../lib/dashboard.js";
import { formatMoney } from "../../lib/format.js";
import ChartCard, { LegendItem } from "./ChartCard.jsx";
import ChartTooltip from "./ChartTooltip.jsx";

const NAMES = { income: "Income", spending: "Spending" };
const AXIS_TICK = { fill: "var(--axis-text)", fontSize: 12 };
const SERIES = [
  { key: "income", color: "var(--series-1)" },
  { key: "spending", color: "var(--series-2)" },
];
// With only a few periods every point gets a dot, so short ranges don't read as bare lines.
const DOTS_UP_TO = 12;

/** Square pixel marker (>= 8px) with a 2px surface ring, centred on the point. */
function PixelDot({ cx, cy, size = 8, color }) {
  if (cx == null || cy == null) return null;
  return (
    <rect
      x={cx - size / 2}
      y={cy - size / 2}
      width={size}
      height={size}
      fill={color}
      stroke="var(--surface-solid)"
      strokeWidth={2}
      shapeRendering="crispEdges"
    />
  );
}

/** Last point of each line: an emphasized end marker. */
function EndDot({ index, count, ...p }) {
  if (index !== count - 1) return null;
  return <PixelDot {...p} size={10} />;
}

/**
 * Income vs spending per week/month: two smooth lines over a faint area wash, one shared
 * y-axis, crosshair tooltip. Lines (not stacked areas) so the two series can cross freely.
 */
export default function IncomeSpendingChart({ series, currency, granularity }) {
  const data = toChartSeries(series);
  const showDots = data.length <= DOTS_UP_TO;
  return (
    <ChartCard
      title="Income vs spending"
      subtitle={`Per ${granularity}. Transfers between your own accounts are excluded.`}
      legend={
        <div className="flex items-center gap-3">
          <LegendItem shape="line" color="var(--series-1)">Income</LegendItem>
          <LegendItem shape="line" color="var(--series-2)">Spending</LegendItem>
        </div>
      }
      renderChart={() => (
        <div className="h-72" role="img" aria-label="Income and spending per period; switch to Table for values">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: 0 }}>
              <defs>
                {SERIES.map((s) => (
                  <linearGradient key={s.key} id={`wash-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={s.color} stopOpacity={0.16} />
                    <stop offset="100%" stopColor={s.color} stopOpacity={0} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={{ stroke: "var(--axis)" }}
                tick={AXIS_TICK}
                minTickGap={12}
                padding={{ left: 12, right: 12 }}
              />
              <YAxis
                tickFormatter={(v) => formatCompact(v, currency)}
                tickLine={false}
                axisLine={false}
                tick={AXIS_TICK}
                width={56}
              />
              <Tooltip
                cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
                content={<ChartTooltip currency={currency} names={NAMES} />}
              />
              {SERIES.map((s) => (
                <Area
                  key={s.key}
                  type="linear"
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill={`url(#wash-${s.key})`}
                  dot={
                    showDots
                      ? (p) => <PixelDot key={p.index} cx={p.cx} cy={p.cy} color={s.color} />
                      : (p) => <EndDot key={p.index} cx={p.cx} cy={p.cy} index={p.index} count={data.length} color={s.color} />
                  }
                  activeDot={(p) => <PixelDot key={`a${p.index}`} cx={p.cx} cy={p.cy} size={12} color={s.color} />}
                  isAnimationActive={false}
                />
              ))}
            </AreaChart>
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
