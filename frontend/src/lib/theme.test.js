import { describe, expect, it } from "vitest";
import { applyTheme, readThemePref, resolveTheme, writeThemePref } from "./theme.js";

describe("theme", () => {
  function fakeStorage(initial = {}) {
    const data = { ...initial };
    return { getItem: (k) => data[k] ?? null, setItem: (k, v) => (data[k] = v), data };
  }

  it("defaults to dark and ignores junk", () => {
    expect(readThemePref(fakeStorage())).toBe("dark");
    expect(readThemePref(fakeStorage({ "sw-theme": "purple" }))).toBe("dark");
    expect(readThemePref(fakeStorage({ "sw-theme": "system" }))).toBe("system");
  });

  it("survives blocked storage", () => {
    const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(readThemePref(blocked)).toBe("dark");
    expect(() => writeThemePref("dark", blocked)).not.toThrow();
  });

  it("round-trips a choice", () => {
    const s = fakeStorage();
    writeThemePref("dark", s);
    expect(readThemePref(s)).toBe("dark");
  });

  it("resolves system against the OS preference", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
  });

  it("applies class, data attribute and color-scheme", () => {
    const classes = new Set();
    const root = {
      classList: { toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)) },
      dataset: {},
      style: {},
    };
    applyTheme("dark", root);
    expect(classes.has("dark")).toBe(true);
    expect(root.dataset.theme).toBe("dark");
    expect(root.style.colorScheme).toBe("dark");
    applyTheme("light", root);
    expect(classes.has("dark")).toBe(false);
  });
});
