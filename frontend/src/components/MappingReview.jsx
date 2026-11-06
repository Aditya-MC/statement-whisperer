import { useMemo, useState } from "react";
import { api } from "../lib/api.js";
import {
  AMOUNT_MODES,
  DATE_FORMAT_PRESETS,
  DECIMAL_SEPARATORS,
  THOUSANDS_SEPARATORS,
  initialMapping,
  toPayload,
  validateMapping,
} from "../lib/mapping.js";
import { Field } from "./ui.jsx";

function ColumnSelect({ value, onChange, columns, allowNone = false }) {
  return (
    <select
      className="input"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
    >
      {(allowNone || value == null) && <option value="">{allowNone ? "— none —" : "Choose…"}</option>}
      {columns.map((c, i) => (
        <option key={i} value={i}>
          {i + 1}. {c || `(column ${i + 1})`}
        </option>
      ))}
    </select>
  );
}

/**
 * Lets the user correct the column mapping of an import that failed validation (or that
 * couldn't be detected automatically) and re-run it with the same file.
 */
export default function MappingReview({ imp, file, accountCurrency, onResolved }) {
  const columns = imp.columns ?? [];
  const [m, setM] = useState(() => initialMapping(imp, accountCurrency ?? "USD"));
  const [retryFile, setRetryFile] = useState(file);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const errors = useMemo(() => validateMapping(m, columns.length), [m, columns.length]);
  const suggestions = imp.validation?.suggestions?.date_format ?? [];
  const set = (k) => (v) => setM((prev) => ({ ...prev, [k]: v }));

  if (!columns.length) return null;

  async function submit(e) {
    e.preventDefault();
    if (Object.keys(errors).length || !retryFile) return;
    setBusy(true);
    setError(null);
    try {
      onResolved(await api.retryImport({ importId: imp.id, file: retryFile, mapping: toPayload(m) }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleDescription(i) {
    setM((prev) => {
      const cur = prev.description_columns ?? [];
      return { ...prev, description_columns: cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i] };
    });
  }

  return (
    <section className="card">
      <h2 className="text-base font-semibold">Review column mapping</h2>
      <p className="mb-4 text-sm text-ink-2">
        Tell us which column holds what. Nothing is saved until the statement passes validation.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-5">
        <fieldset className="grid gap-4 sm:grid-cols-2">
          <Field label="Date column" error={errors.date_column}>
            <ColumnSelect value={m.date_column} onChange={set("date_column")} columns={columns} />
          </Field>
          <Field label="Running balance column" error={errors.balance_column} hint="Strongly recommended: used to verify every row.">
            <ColumnSelect value={m.balance_column} onChange={set("balance_column")} columns={columns} allowNone />
          </Field>
        </fieldset>

        <Field label="Description column(s)" error={errors.description_columns}>
          <div className="flex flex-wrap gap-2">
            {columns.map((c, i) => (
              <label
                key={i}
                className={`cursor-pointer rounded-md border px-2 py-1 text-sm ${
                  m.description_columns?.includes(i) ? "border-ink bg-surface-2" : "border-line"
                }`}
              >
                <input type="checkbox" className="sr-only" checked={m.description_columns?.includes(i) ?? false} onChange={() => toggleDescription(i)} />
                {c || `(column ${i + 1})`}
              </label>
            ))}
          </div>
        </Field>

        <Field label="How are amounts shown?">
          <div className="flex flex-col gap-1.5">
            {AMOUNT_MODES.map((mode) => (
              <label key={mode.value} className="flex items-center gap-2 text-sm">
                <input type="radio" name="amount_mode" checked={m.amount_mode === mode.value} onChange={() => set("amount_mode")(mode.value)} />
                {mode.label}
              </label>
            ))}
          </div>
        </Field>

        <fieldset className="grid gap-4 sm:grid-cols-2">
          {m.amount_mode === "debit_credit" ? (
            <>
              <Field label="Debit (money out) column" error={errors.debit_column}>
                <ColumnSelect value={m.debit_column} onChange={set("debit_column")} columns={columns} />
              </Field>
              <Field label="Credit (money in) column" error={errors.credit_column}>
                <ColumnSelect value={m.credit_column} onChange={set("credit_column")} columns={columns} />
              </Field>
            </>
          ) : (
            <Field label="Amount column" error={errors.amount_column}>
              <ColumnSelect value={m.amount_column} onChange={set("amount_column")} columns={columns} />
            </Field>
          )}
          {m.amount_mode === "amount_with_type" && (
            <Field label="Debit/credit type column" error={errors.type_column}>
              <ColumnSelect value={m.type_column} onChange={set("type_column")} columns={columns} />
            </Field>
          )}
          {m.amount_mode === "signed" && (
            <Field label="Sign convention">
              <select className="input" value={m.sign_convention} onChange={(e) => set("sign_convention")(e.target.value)}>
                <option value="negative_is_debit">Negative = money out (bank accounts)</option>
                <option value="positive_is_debit">Positive = money out (credit cards)</option>
              </select>
            </Field>
          )}
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-4">
          <Field label="Date format" error={errors.date_format} hint="Python strptime, e.g. %d/%m/%Y">
            <input className="input font-mono" list="date-formats" value={m.date_format} onChange={(e) => set("date_format")(e.target.value)} />
            <datalist id="date-formats">
              {DATE_FORMAT_PRESETS.map((f) => (
                <option key={f} value={f} />
              ))}
            </datalist>
          </Field>
          <Field label="Decimal separator">
            <select className="input" value={m.decimal_separator} onChange={(e) => set("decimal_separator")(e.target.value)}>
              {DECIMAL_SEPARATORS.map((s) => (
                <option key={s} value={s}>
                  {s === "." ? "Dot  1.50" : "Comma  1,50"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Thousands separator" error={errors.thousands_separator}>
            <select className="input" value={m.thousands_separator} onChange={(e) => set("thousands_separator")(e.target.value)}>
              {THOUSANDS_SEPARATORS.map((s) => (
                <option key={s.label} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Currency" error={errors.currency}>
            <input className="input uppercase" maxLength={3} value={m.currency} onChange={(e) => set("currency")(e.target.value)} />
          </Field>
        </fieldset>

        {suggestions.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-ink-2">Date formats that fit every row:</span>
            {suggestions.map((f) => (
              <button key={f} type="button" className="btn-ghost font-mono !py-0.5" onClick={() => set("date_format")(f)}>
                {f}
              </button>
            ))}
          </div>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={m.drcr_markers} onChange={(e) => set("drcr_markers")(e.target.checked)} />
          Amounts or balances end in Dr / Cr (e.g. “1,200.00 Dr”)
        </label>

        {!file && (
          <Field label="Statement file" hint="Uploads aren't kept on the server, so pick the same file again.">
            <input type="file" accept=".csv,.tsv,.txt,.xlsx" className="input" onChange={(e) => setRetryFile(e.target.files?.[0] ?? null)} />
          </Field>
        )}

        {error && <p className="text-sm text-critical">{error}</p>}
        <div>
          <button className="btn-primary" disabled={busy || Object.keys(errors).length > 0 || !retryFile}>
            {busy ? "Re-running…" : "Re-run import with this mapping"}
          </button>
        </div>
      </form>
    </section>
  );
}
