import { useEffect } from "react";

export function Toast({ message, tone = "info", onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4500);
    return () => clearTimeout(t);
  }, [onClose]);
  return (
    <div role="status" className="fixed inset-x-0 bottom-5 z-50 flex justify-center px-4">
      <div className="flex max-w-lg items-start gap-3 rounded-md bg-ink px-4 py-2.5 text-sm text-page shadow-lg">
        {tone !== "info" && <Dot tone={tone === "error" ? "critical" : "good"} />}
        <span>{message}</span>
        <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" aria-label="Dismiss">
          ✕
        </button>
      </div>
    </div>
  );
}

const DOT_COLORS = {
  good: "bg-[#0ca30c]",
  warning: "bg-[#fab219]",
  critical: "bg-[#d03b3b]",
  neutral: "bg-muted",
};

/** Status dot (fixed status palette). Always paired with a text label - never color alone. */
export function Dot({ tone = "neutral" }) {
  return <span aria-hidden="true" className={`mt-1.5 inline-block size-2 shrink-0 rounded-full ${DOT_COLORS[tone]}`} />;
}

const STATUS_TONE = { completed: "good", needs_review: "warning", failed: "critical" };

export function StatusPill({ status }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs font-medium text-ink-2 [&>span]:mt-0">
      <Dot tone={STATUS_TONE[status]} />
      {status.replace("_", " ")}
    </span>
  );
}

/** Neutral hairline chip. Identity comes from the text, not from color. */
export function Badge({ children, title }) {
  return (
    <span title={title} className="rounded border border-line px-1.5 py-px text-[11px] font-medium text-muted">
      {children}
    </span>
  );
}

export function Field({ label, error, children, hint }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-ink-2">{label}</span>
      {children}
      {hint && !error && <span className="text-xs text-muted">{hint}</span>}
      {error && <span className="text-xs text-critical">{error}</span>}
    </label>
  );
}

/** Two-option segmented switch (used for Chart | Table). */
export function Segmented({ options, value, onChange, label }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
            value === o.value ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
