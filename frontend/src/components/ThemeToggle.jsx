import { useEffect, useState } from "react";
import { applyTheme, readThemePref, resolveTheme, writeThemePref } from "../lib/theme.js";
import { IconMonitor, IconMoon, IconSun } from "./icons.jsx";

const ICONS = { light: IconSun, dark: IconMoon, system: IconMonitor };
const LABELS = { light: "Light", dark: "Dark", system: "System" };
const ORDER = ["system", "light", "dark"];

function useThemePref() {
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
  return [pref, setPref];
}

/**
 * Theme switch. `segmented` (default): Light / Dark / System pill. `cycle`: one round button
 * for the navigation rail that steps System → Light → Dark. "System" follows the OS live.
 */
export default function ThemeToggle({ variant = "segmented", className = "" }) {
  const [pref, setPref] = useThemePref();

  if (variant === "cycle") {
    const Icon = ICONS[pref];
    const next = ORDER[(ORDER.indexOf(pref) + 1) % ORDER.length];
    return (
      <button
        type="button"
        title={`Theme: ${LABELS[pref]} (switch to ${LABELS[next]})`}
        aria-label={`Theme: ${LABELS[pref]}. Switch to ${LABELS[next]}`}
        onClick={() => setPref(next)}
        className={className}
      >
        <Icon size={20} />
      </button>
    );
  }

  return (
    <div role="radiogroup" aria-label="Theme" className={`inline-flex rounded-full bg-surface-2 p-1 ${className}`}>
      {Object.keys(LABELS).map((key) => {
        const Icon = ICONS[key];
        return (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={pref === key}
            title={LABELS[key]}
            onClick={() => setPref(key)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition ${
              pref === key ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
            }`}
          >
            <Icon size={14} />
            <span className="hidden sm:inline">{LABELS[key]}</span>
          </button>
        );
      })}
    </div>
  );
}
