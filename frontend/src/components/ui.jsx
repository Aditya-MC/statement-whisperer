import { useEffect } from "react";

export function Toast({ message, tone = "info", onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4500);
    return () => clearTimeout(t);
  }, [onClose]);
  return (
    <div role="status" className="fixed inset-x-0 bottom-24 z-50 flex justify-center px-4 md:bottom-6">
      <div className="pop-in flex max-w-lg items-start gap-3 border-2 border-(--glass-border) bg-surface-solid px-4 py-3 text-sm text-ink" style={{ boxShadow: "var(--primary-glow)" }}>
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
    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-2.5 py-0.5 text-xs font-medium text-ink-2 [&>span]:mt-0">
      <Dot tone={STATUS_TONE[status]} />
      {status.replace("_", " ")}
    </span>
  );
}

/** Soft neutral chip. Identity comes from the text, not from color. */
export function Badge({ children, title }) {
  return (
    <span title={title} className="rounded-full bg-surface-2 px-2 py-px text-[11px] font-medium text-muted">
      {children}
    </span>
  );
}

export function Field({ label, error, children, hint }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="pl-1 text-xs font-medium text-muted">{label}</span>
      {children}
      {hint && !error && <span className="pl-1 text-xs text-muted">{hint}</span>}
      {error && <span className="pl-1 text-xs text-critical">{error}</span>}
    </label>
  );
}

/** iOS-style segmented control (used for Chart | Table). */
export function Segmented({ options, value, onChange, label }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full bg-surface-2 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-full px-3 py-1 text-xs font-medium transition ${
            value === o.value ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Large page title + one-line subtitle, with optional actions on the right. */
export function PageHeader({ title, subtitle, children }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-pixel text-4xl leading-none font-normal text-balance uppercase md:text-5xl">
          {title}
          <span aria-hidden="true" className="cursor-blink">_</span>
        </h1>
        {subtitle && <p className="mt-2 text-[15px] text-ink-2">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  );
}

/** Round icon chip used in the top-right corner of stat cards. */
export function IconChip({ children }) {
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-2 text-ink-2" aria-hidden="true">
      {children}
    </span>
  );
}
