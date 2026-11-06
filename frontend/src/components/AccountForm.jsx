import { useState } from "react";
import { api } from "../lib/api.js";
import { Field } from "./ui.jsx";

/** Create an account. Only the last 4 digits of the account number are ever asked for. */
export default function AccountForm({ onCreated, onCancel }) {
  const [form, setForm] = useState({ bank_name: "", nickname: "", currency: "INR", last4: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const acct = await api.createAccount({ ...form, last4: form.last4 || null });
      onCreated(acct);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
      <Field label="Bank">
        <input className="input" required value={form.bank_name} onChange={set("bank_name")} placeholder="Example Bank" />
      </Field>
      <Field label="Nickname">
        <input className="input" required value={form.nickname} onChange={set("nickname")} placeholder="Salary account" />
      </Field>
      <Field label="Currency">
        <input className="input uppercase" required maxLength={3} value={form.currency} onChange={set("currency")} />
      </Field>
      <Field label="Last 4 digits" hint="Optional. Never the full number.">
        <input className="input" inputMode="numeric" pattern="\d{4}" maxLength={4} value={form.last4} onChange={set("last4")} />
      </Field>
      {error && <p className="text-sm text-red-600 sm:col-span-4">{error}</p>}
      <div className="flex gap-2 sm:col-span-4">
        <button className="btn-primary" disabled={busy}>Create account</button>
        {onCancel && (
          <button type="button" className="btn-ghost" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
