import { describe, expect, it } from "vitest";
import { categoryLabels, groupCategories } from "./categories.js";
import { amountTone, formatDate, formatMoney } from "./format.js";

describe("formatMoney", () => {
  it("formats decimal strings with the currency", () => {
    expect(formatMoney("-1234.5", "USD", "en-US")).toBe("-$1,234.50");
    expect(formatMoney("1234.5", "INR", "en-IN")).toBe("₹1,234.50");
  });

  it("tolerates empty and odd input", () => {
    expect(formatMoney(null)).toBe("");
    expect(formatMoney("abc")).toBe("abc");
    expect(formatMoney("10", "NOTACODE", "en-US")).toBe("10.00");
  });
});

describe("formatDate", () => {
  it("formats ISO dates without timezone shifts", () => {
    expect(formatDate("2024-01-05")).toBe("05 Jan 2024");
    expect(formatDate("")).toBe("");
  });
});

describe("amountTone", () => {
  it("highlights money in", () => {
    expect(amountTone("5")).toBe("text-good");
    expect(amountTone("-5")).toBe("text-ink");
  });
});

describe("categories", () => {
  const cats = [
    { id: 1, name: "Food", parent_id: null, kind: "expense" },
    { id: 2, name: "Restaurants", parent_id: 1, kind: "expense" },
    { id: 3, name: "Groceries", parent_id: 1, kind: "expense" },
    { id: 4, name: "Income", parent_id: null, kind: "income" },
    { id: 5, name: "Salary", parent_id: 4, kind: "income" },
  ];

  it("groups and sorts leaves under parents", () => {
    const groups = groupCategories(cats);
    expect(groups.map((g) => g.name)).toEqual(["Food", "Income"]);
    expect(groups[0].options.map((o) => o.name)).toEqual(["Groceries", "Restaurants"]);
  });

  it("builds readable labels", () => {
    const labels = categoryLabels(cats);
    expect(labels.get(3)).toBe("Food › Groceries");
    expect(labels.get(4)).toBe("Income");
  });
});
