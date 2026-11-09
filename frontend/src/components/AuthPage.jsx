import { useState } from "react";
import { api } from "../lib/api.js";
import PrivacyPage from "./PrivacyPage.jsx";
import ThemeToggle from "./ThemeToggle.jsx";
import { Field } from "./ui.jsx";

/**
 * Sign in / create account. `firstRun` (nobody has signed up yet) shows the one-time admin
 * set-up; afterwards new accounts need an invite code.
 */
export default function AuthPage({ firstRun, aiEnabled, onSignedIn }) {
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [mode, setMode] = useState(firstRun ? "signup" : "login");
  const [form, setForm] = useState({ email: "", password: "", invite_code: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const signup = mode === "signup";

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = signup
        ? await api.signup({ email: form.email, password: form.password, invite_code: form.invite_code || null })
        : await api.login({ email: form.email, password: form.password });
      onSignedIn(user);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (showPrivacy) {
    return (
      <div className="min-h-screen px-4 py-10">
        <PrivacyPage aiEnabled={aiEnabled} onBack={() => setShowPrivacy(false)} />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex justify-end px-4 py-3">
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-[10vh]">
        <div className="w-full max-w-sm">
          <h1 className="text-2xl font-semibold tracking-tight">Statement Whisperer</h1>
          <p className="mt-1 mb-8 text-sm text-ink-2">A private ledger that reads any bank's statement.</p>

          <form onSubmit={submit} className="card flex flex-col gap-4">
            <h2 className="text-sm font-semibold">
              {firstRun ? "Create the admin account" : signup ? "Create your account" : "Sign in"}
            </h2>
            {firstRun && (
              <p className="text-xs text-ink-2">
                You're the first person here, so this account becomes the admin. Any existing ledger data on this
                server will be yours.
              </p>
            )}
            <Field label="Email">
              <input className="input" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
            </Field>
            <Field label="Password" hint={signup ? "At least 10 characters." : undefined}>
              <input
                className="input"
                type="password"
                autoComplete={signup ? "new-password" : "current-password"}
                required
                minLength={signup ? 10 : undefined}
                value={form.password}
                onChange={set("password")}
              />
            </Field>
            {signup && !firstRun && (
              <Field label="Invite code" hint="Ask the person who invited you.">
                <input className="input font-mono" required value={form.invite_code} onChange={set("invite_code")} />
              </Field>
            )}
            {error && <p className="text-sm text-critical">{error}</p>}
            <button className="btn-primary justify-center" disabled={busy}>
              {busy ? "Please wait…" : signup ? "Create account" : "Sign in"}
            </button>
          </form>

          {!firstRun && (
            <p className="mt-4 text-center text-sm text-ink-2">
              {signup ? "Already have an account? " : "Have an invite code? "}
              <button
                type="button"
                className="font-medium text-ink underline-offset-2 hover:underline"
                onClick={() => {
                  setMode(signup ? "login" : "signup");
                  setError(null);
                }}
              >
                {signup ? "Sign in" : "Create an account"}
              </button>
            </p>
          )}
          <p className="mt-8 text-center text-xs text-muted">
            Your statements are processed in memory and never stored. Only you can see your data.{" "}
            <button type="button" className="underline underline-offset-2 hover:text-ink" onClick={() => setShowPrivacy(true)}>
              Privacy
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
