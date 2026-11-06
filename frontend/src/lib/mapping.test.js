import { describe, expect, it } from "vitest";
import { guessMapping, initialMapping, toPayload, validateMapping } from "./mapping.js";

describe("guessMapping", () => {
  it("finds debit/credit layouts from Indian-bank headers", () => {
    const m = guessMapping(
      ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
      "INR",
    );
    expect(m).toMatchObject({
      date_column: 0,
      description_columns: [1],
      amount_mode: "debit_credit",
      debit_column: 4,
      credit_column: 5,
      balance_column: 6,
      currency: "INR",
    });
  });

  it("finds a signed amount column", () => {
    const m = guessMapping(["Posting Date", "Description", "Amount", "Running Bal."]);
    expect(m).toMatchObject({ amount_mode: "signed", amount_column: 2, balance_column: 3 });
  });

  it("finds amount + type layouts", () => {
    const m = guessMapping(["Date", "Details", "Type", "Amount", "Balance"]);
    expect(m).toMatchObject({ amount_mode: "amount_with_type", type_column: 2, amount_column: 3 });
  });
});

describe("validateMapping", () => {
  const ok = guessMapping(["Date", "Description", "Amount", "Balance"]);

  it("accepts a complete mapping", () => {
    expect(validateMapping(ok, 4)).toEqual({});
  });

  it("flags missing mode columns, bad separators and out-of-range columns", () => {
    const errors = validateMapping(
      { ...ok, amount_mode: "debit_credit", debit_column: 2, credit_column: 2, balance_column: 9,
        thousands_separator: ".", decimal_separator: ".", currency: "rupees" },
      4,
    );
    expect(Object.keys(errors).sort()).toEqual(
      ["balance_column", "credit_column", "currency", "thousands_separator"].sort(),
    );
  });

  it("requires a description column and a strptime date format", () => {
    const errors = validateMapping({ ...ok, description_columns: [], date_format: "dd/mm/yyyy" }, 4);
    expect(errors).toHaveProperty("description_columns");
    expect(errors).toHaveProperty("date_format");
  });
});

describe("toPayload", () => {
  it("clears columns that don't apply to the amount mode", () => {
    const p = toPayload({ amount_mode: "signed", amount_column: 2, debit_column: 3, credit_column: 4,
      type_column: 5, currency: "usd" });
    expect(p).toMatchObject({ amount_column: 2, debit_column: null, credit_column: null, type_column: null,
      currency: "USD" });
  });
});

describe("initialMapping", () => {
  it("prefers the stored mapping, otherwise guesses from columns", () => {
    expect(initialMapping({ mapping: { currency: "EUR" } }, "USD")).toEqual({ currency: "EUR" });
    expect(initialMapping({ mapping: null, columns: ["Date", "Memo", "Amount"] }, "GBP").currency).toBe("GBP");
  });
});
