import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.js";
import { Field } from "./ui.jsx";

function Invites({ notify }) {
  const [invites, setInvites] = useState([]);
  const [note, setNote] = useState("");

  const load = useCallback(() => {
    api.listInvites().then(setInvites).catch((e) => notify(e.message, "error"));
  }, [notify]);
  useEffect(load, [load]);

  async function create(e) {
    e.preventDefault();
    try {
      const inv = await api.createInvite(note);
      setNote("");
      load();
      try {
        await navigator.clipboard.writeText(inv.code);
        notify("Invite created and copied to the clipboard.", "success");
      } catch {
        notify("Invite created.", "success");
      }
    } catch (err) {
      notify(err.message, "error");
    }
  }

  return (
    <section className="card flex flex-col gap-4">
      <div>
        <h2 className="text-[17px] font-semibold tracking-tight">Invite testers</h2>
        <p className="mt-0.5 text-sm text-ink-2">
          Each code works once. Send it with the app's link; they sign up with it and get their own private ledger.
        </p>
      </div>
      <form onSubmit={create} className="flex flex-wrap items-end gap-3">
        <Field label="Note (only you see it)">
          <input className="input w-64" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Priya" />
        </Field>
        <button className="btn-primary">Create invite</button>
      </form>
      {invites.length > 0 && (
        <table className="w-full text-sm">
          <thead className="eyebrow text-left">
            <tr className="border-b border-line">
              <th className="py-2 font-medium">Code</th>
              <th className="py-2 font-medium">Note</th>
              <th className="py-2 font-medium">Created</th>
              <th className="py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {invites.map((i) => (
              <tr key={i.id} className="border-b border-line last:border-0">
                <td className="py-1.5">
                  <button
                    type="button"
                    title="Copy"
                    className="font-mono hover:underline disabled:no-underline"
                    disabled={!!i.used_at}
                    onClick={() => navigator.clipboard?.writeText(i.code).then(() => notify("Copied.", "success"))}
                  >
                    {i.code}
                  </button>
                </td>
                <td className="py-1.5 text-ink-2">{i.note ?? "—"}</td>
                <td className="py-1.5 text-muted">{formatDate(i.created_at)}</td>
                <td className="py-1.5 text-muted">{i.used_at ? `Used ${formatDate(i.used_at)}` : "Unused"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function DeleteAccount({ onDeleted, notify }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.deleteMe(password);
      onDeleted();
    } catch (err) {
      notify(err.message, "error");
      setBusy(false);
    }
  }

  return (
    <section className="card flex flex-col gap-3 border-critical/40">
      <div>
        <h2 className="text-[17px] font-semibold tracking-tight">Delete account</h2>
        <p className="mt-0.5 text-sm text-ink-2">
          Permanently deletes your account and everything in it: accounts, imports, transactions, categories and rules.
          This can't be undone.
        </p>
      </div>
      {!open ? (
        <div>
          <button type="button" className="btn-ghost text-critical" onClick={() => setOpen(true)}>
            Delete my account…
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <Field label="Confirm with your password">
            <input className="input w-64" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <button className="btn bg-critical text-white hover:opacity-90" disabled={busy}>
            {busy ? "Deleting…" : "Delete everything"}
          </button>
          <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
            Cancel
          </button>
        </form>
      )}
    </section>
  );
}

export default function AccountPage({ user, onSignOut, onDeleted, onShowPrivacy, notify }) {
  return (
    <div className="flex flex-col gap-6">
      <section className="card flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[17px] font-semibold tracking-tight">{user.email}</h2>
          <p className="mt-0.5 text-xs text-muted">
            {user.is_admin ? "Admin · " : ""}Member since {formatDate(user.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* A plain link: the browser downloads the JSON with the session cookie. */}
          <a className="btn-ghost" href="/api/auth/me/export" download>
            Download my data
          </a>
          <button type="button" className="btn-ghost" onClick={onShowPrivacy}>
            Privacy
          </button>
          <button type="button" className="btn-ghost" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </section>
      {user.is_admin && <Invites notify={notify} />}
      <DeleteAccount onDeleted={onDeleted} notify={notify} />
    </div>
  );
}
