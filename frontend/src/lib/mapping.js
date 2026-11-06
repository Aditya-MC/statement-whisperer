// Column-mapping form logic for the review screen. Mirrors the backend ColumnMapping rules so
// the user gets instant feedback; the backend still validates everything.

export const AMOUNT_MODES = [
  { value: "debit_credit", label: "Separate debit and credit columns" },
  { value: "signed", label: "One amount column (sign shows direction)" },
  { value: "amount_with_type", label: "One amount column plus a Dr/Cr type column" },
];

export const DATE_FORMAT_PRESETS = [
  "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y",
  "%m/%d/%y", "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d",
];

export const DECIMAL_SEPARATORS = [".", ","];
export const THOUSANDS_SEPARATORS = [
  { value: ",", label: "Comma  1,234" },
  { value: ".", label: "Dot  1.234" },
  { value: " ", label: "Space  1 234" },
  { value: "'", label: "Apostrophe  1'234" },
  { value: "", label: "None  1234" },
];

const COLUMN_FIELDS = ["amount_column", "debit_column", "credit_column", "type_column", "balance_column"];

const HINTS = {
  date_column: /\b(txn|tran|transaction|posting|value|book)?\s*(date|dt|datum|buchungstag)\b/i,
  description: /narration|description|particulars|details|memo|narrative|remarks|verwendungszweck|omschrijving|booking text/i,
  debit_column: /withdraw|debit|paid out|\bdr\b|money out/i,
  credit_column: /deposit|credit|paid in|\bcr\b|money in/i,
  amount_column: /amount|betrag|bedrag/i,
  balance_column: /balance|bal\b|saldo/i,
  type_column: /^type$|dr\s*\/\s*cr|cr\s*\/\s*dr/i,
};

/**
 * Best-effort mapping from header names, used when automatic detection was unavailable.
 * The user always confirms it before anything is imported.
 */
export function guessMapping(columns, currency = "USD") {
  const find = (re, exclude = []) => {
    const i = columns.findIndex((c, idx) => re.test(c) && !exclude.includes(idx));
    return i === -1 ? null : i;
  };
  const date = find(HINTS.date_column) ?? 0;
  const balance = find(HINTS.balance_column, [date]);
  const debit = find(HINTS.debit_column, [date, balance]);
  const credit = find(HINTS.credit_column, [date, balance, debit]);
  const type = find(HINTS.type_column, [date, balance, debit, credit]);
  const amount = find(HINTS.amount_column, [date, balance, debit, credit, type]);
  const desc = find(HINTS.description, [date]);

  let amount_mode = "signed";
  if (debit !== null && credit !== null) amount_mode = "debit_credit";
  else if (amount !== null && type !== null) amount_mode = "amount_with_type";

  return {
    date_column: date,
    description_columns: desc === null ? [] : [desc],
    amount_mode,
    amount_column: amount_mode === "debit_credit" ? null : amount,
    debit_column: amount_mode === "debit_credit" ? debit : null,
    credit_column: amount_mode === "debit_credit" ? credit : null,
    type_column: amount_mode === "amount_with_type" ? type : null,
    balance_column: balance,
    date_format: "%d/%m/%Y",
    decimal_separator: ".",
    thousands_separator: ",",
    currency,
    sign_convention: "negative_is_debit",
    drcr_markers: false,
  };
}

/** Returns {field: message}; empty object means the mapping can be submitted. */
export function validateMapping(m, columnCount) {
  const errors = {};
  const inRange = (v) => v === null || v === undefined || (Number.isInteger(v) && v >= 0 && v < columnCount);

  if (!Number.isInteger(m.date_column) || !inRange(m.date_column)) errors.date_column = "Pick the date column";
  if (!m.description_columns?.length) errors.description_columns = "Pick at least one description column";
  else if (!m.description_columns.every(inRange)) errors.description_columns = "Unknown column";
  for (const f of COLUMN_FIELDS) if (!inRange(m[f])) errors[f] = "Unknown column";

  if (m.amount_mode === "signed" && m.amount_column == null) errors.amount_column = "Pick the amount column";
  if (m.amount_mode === "debit_credit") {
    if (m.debit_column == null) errors.debit_column = "Pick the debit (money out) column";
    if (m.credit_column == null) errors.credit_column = "Pick the credit (money in) column";
    if (m.debit_column != null && m.debit_column === m.credit_column)
      errors.credit_column = "Debit and credit must be different columns";
  }
  if (m.amount_mode === "amount_with_type") {
    if (m.amount_column == null) errors.amount_column = "Pick the amount column";
    if (m.type_column == null) errors.type_column = "Pick the debit/credit type column";
  }
  if (!m.date_format || !m.date_format.includes("%")) errors.date_format = "Use a format like %d/%m/%Y";
  if (m.decimal_separator === m.thousands_separator) errors.thousands_separator = "Must differ from the decimal separator";
  if (!/^[A-Za-z]{3}$/.test(m.currency ?? "")) errors.currency = "3-letter code, e.g. INR";
  return errors;
}

/** Clean payload for the API: only the columns relevant to the amount mode are sent. */
export function toPayload(m) {
  const p = { ...m, currency: (m.currency || "").toUpperCase() };
  if (p.amount_mode === "debit_credit") {
    p.amount_column = null;
    p.type_column = null;
  } else {
    p.debit_column = null;
    p.credit_column = null;
    if (p.amount_mode === "signed") p.type_column = null;
  }
  return p;
}

/** Mapping stored on an import (may be null when detection failed). */
export function initialMapping(imp, accountCurrency) {
  return imp.mapping ? { ...imp.mapping } : guessMapping(imp.columns ?? [], accountCurrency);
}
