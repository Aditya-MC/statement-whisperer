// Light / dark / system theme. The choice is a per-browser convenience stored in localStorage
// (wrapped in try/catch: storage can be blocked); the page works without it.

export const THEME_KEY = "sw-theme";
export const THEMES = ["light", "dark", "system"];

export function readThemePref(storage = globalThis.localStorage) {
  try {
    const v = storage?.getItem(THEME_KEY);
    return THEMES.includes(v) ? v : "system";
  } catch {
    return "system";
  }
}

export function writeThemePref(pref, storage = globalThis.localStorage) {
  try {
    storage?.setItem(THEME_KEY, pref);
  } catch {
    /* storage unavailable: the choice just won't persist */
  }
}

/** "system" follows the OS; otherwise the explicit choice wins. */
export function resolveTheme(pref, systemPrefersDark) {
  if (pref === "light" || pref === "dark") return pref;
  return systemPrefersDark ? "dark" : "light";
}

/** Apply to <html>: the `dark` class drives Tailwind; data-theme and color-scheme drive native UI. */
export function applyTheme(resolved, root = globalThis.document?.documentElement) {
  if (!root) return;
  root.classList.toggle("dark", resolved === "dark");
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
}
