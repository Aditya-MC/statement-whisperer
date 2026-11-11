import { useState } from "react";
import { Segmented } from "../ui.jsx";

const VIEWS = [
  { value: "chart", label: "Chart" },
  { value: "table", label: "Table" },
];

/**
 * Card with a title and an optional Chart | Table switch. Every chart has a table twin, so
 * no value is reachable only by hovering.
 */
export default function ChartCard({ title, subtitle, legend, renderChart, renderTable, className = "" }) {
  const [view, setView] = useState("chart");
  const hasToggle = renderChart && renderTable;
  return (
    <section className={`card flex flex-col gap-4 ${className}`}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[17px] font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-4">
          {legend && view === "chart" && legend}
          {hasToggle && <Segmented label={`${title} view`} options={VIEWS} value={view} onChange={setView} />}
        </div>
      </header>
      {view === "chart" && renderChart ? renderChart() : renderTable?.()}
    </section>
  );
}

/** Legend entry for bar series: a small rect swatch (mirrors the mark) + text in ink, never colored text. */
export function LegendItem({ color, children }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ background: color }} />
      {children}
    </span>
  );
}
