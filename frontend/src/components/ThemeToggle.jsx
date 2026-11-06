import { useEffect, useState } from "react";
import { applyTheme, readThemePref, resolveTheme, writeThemePref } from "../lib/theme.js";

const icon = {
  light: (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" strokeLinecap="round" />
    </svg>
  ),
  dark: (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" strokeLinejoin="round" />
    </svg>
  ),
  system: (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="2" y="3" width="12" height="8" rx="1" />
      <path d="M6 14h4M8 11v3" strokeLinecap="round" />
    </svg>
  ),
};

const LABELS = { light: "Light", dark: "Dark", system: "System" };

/** Light / Dark / System segmented switch. "System" follows the OS live. */
export default function ThemeToggle() {
  const [pref, setPref] = useState(readThemePref);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => applyTheme(resolveTheme(pref, mq.matches));
    sync();
    writeThemePref(pref);
    if (pref !== "system") return undefined;
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, [pref]);

  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-md border border-line p-0.5">
      {Object.keys(LABELS).map((key) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={pref === key}
          title={LABELS[key]}
          onClick={() => setPref(key)}
          className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium transition-colors ${
            pref === key ? "bg-ink text-page" : "text-muted hover:text-ink"
          }`}
        >
          {icon[key]}
          <span className="hidden sm:inline">{LABELS[key]}</span>
        </button>
      ))}
    </div>
  );
}
