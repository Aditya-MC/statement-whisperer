import { describe, expect, it } from "vitest";
import { formatCompact, formatPercent, presetRange, toChartSeries } from "./dashboard.js";

describe("presetRange", () => {
  const today = new Date(2026, 10, 6); // 6 Nov 2026 (months are 0-based)

  it.each([
    ["this_month", "2026-11-01", "2026-11-06"],
    ["last_month", "2026-10-01", "2026-10-31"],
    ["last_90", "2026-08-09", "2026-11-06"],
    ["last_12m", "2025-12-01", "2026-11-06"],
    ["ytd", "2026-01-01", "2026-11-06"],
  ])("%s", (preset, from, to) => {
    expect(presetRange(preset, today)).toEqual({ date_from: from, date_to: to });
  });

  it("all time and custom are unbounded", () => {
    expect(presetRange("all", today)).toEqual({ date_from: null, date_to: null });
  });

  it("last month in January wraps to December", () => {
    expect(presetRange("last_month", new Date(2027, 0, 15))).toEqual({
      date_from: "2026-12-01",
      date_to: "2026-12-31",
    });
  });
});

describe("formatting", () => {
  it("compacts money for axes", () => {
    expect(formatCompact("12500", "INR", "en-IN")).toBe("₹12.5K");
    expect(formatCompact("950", "USD", "en-US")).toBe("$950");
    expect(formatCompact("abc", "USD")).toBe("");
  });

  it("formats savings rate", () => {
    expect(formatPercent(0.734)).toBe("73%");
    expect(formatPercent(null)).toBe("—");
  });

  it("parses series amounts", () => {
    expect(toChartSeries([{ label: "Oct", income: "10.50", spending: "2.00" }])).toEqual([
      { label: "Oct", income: 10.5, spending: 2 },
    ]);
  });
});
