// Date-range presets and number formatting for the dashboard.

export const PRESETS = [
  { id: "this_month", label: "This month" },
  { id: "last_month", label: "Last month" },
  { id: "last_90", label: "Last 90 days" },
  { id: "last_12m", label: "Last 12 months" },
  { id: "ytd", label: "Year to date" },
  { id: "all", label: "All time" },
  { id: "custom", label: "Custom range" },
];

const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Inclusive {date_from, date_to} ISO strings for a preset (nulls = unbounded). Local dates. */
export function presetRange(preset, today = new Date()) {
  const y = today.getFullYear();
  const m = today.getMonth();
  switch (preset) {
    case "this_month":
      return { date_from: iso(new Date(y, m, 1)), date_to: iso(today) };
    case "last_month":
      return { date_from: iso(new Date(y, m - 1, 1)), date_to: iso(new Date(y, m, 0)) };
    case "last_90":
      return { date_from: iso(new Date(y, m, today.getDate() - 89)), date_to: iso(today) };
    case "last_12m":
      return { date_from: iso(new Date(y, m - 11, 1)), date_to: iso(today) };
    case "ytd":
      return { date_from: iso(new Date(y, 0, 1)), date_to: iso(today) };
    default:
      return { date_from: null, date_to: null };
  }
}

const compactCache = new Map();

/** Axis/label money: ₹12K, $1.2M; full precision under 1,000. */
export function formatCompact(amount, currency, locale = undefined) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return "";
  const key = `${locale}|${currency}`;
  let fmt = compactCache.get(key);
  if (!fmt) {
    try {
      fmt = new Intl.NumberFormat(locale, {
        style: "currency",
        currency,
        notation: "compact",
        maximumFractionDigits: 1,
      });
    } catch {
      fmt = new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 });
    }
    compactCache.set(key, fmt);
  }
  return fmt.format(n);
}

export function formatPercent(ratio) {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio)) return "—";
  return `${Math.round(ratio * 100)}%`;
}

/** Parse the API's decimal strings into numbers for charting (display only, never re-summed). */
export function toChartSeries(series) {
  return series.map((s) => ({ ...s, income: Number(s.income), spending: Number(s.spending) }));
}

/**
 * Pie slice color. The slot comes from the API (the group's all-time rank), so a category keeps
 * its color whatever the filters; null is the gray "Other".
 */
export function sliceColor(slot) {
  return slot === null || slot === undefined ? "var(--series-muted)" : `var(--series-${slot + 1})`;
}
