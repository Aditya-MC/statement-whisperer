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
      <header className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-5 md:px-8">
        <span
          aria-hidden="true"
          style={{ boxShadow: "var(--primary-glow)" }}
          className="grid size-9 place-items-center bg-primary font-pixel text-[15px] font-bold text-on-primary"
        >
          S
        </span>
        <span className="font-pixel text-[15px] uppercase">Statement Whisperer</span>
        <ThemeToggle className="ml-auto" />
      </header>
      <main className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-10 px-4 pt-6 pb-16 md:px-8 lg:grid-cols-[1.15fr_1fr] lg:gap-16">
        <section className="flex flex-col gap-6">
          <p className="font-pixel text-xs tracking-widest text-muted uppercase">Welcome · Please insert statement</p>
          <h1 className="font-pixel text-4xl leading-[1.05] font-bold text-balance uppercase md:text-6xl">
            Your statements, finally making sense<span aria-hidden="true" className="cursor-blink">_</span>
          </h1>
          <p className="max-w-md text-[17px] leading-relaxed text-ink-2">
            Drop in a CSV or Excel export from any bank. Every row is checked against the bank's own running
            balance, sorted into categories and turned into a clear picture of where your money goes.
          </p>
          <ul className="flex flex-wrap gap-2 text-xs text-ink-2">
            {["Any bank's layout", "Balances verified row by row", "Files never stored"].map((t) => (
              <li key={t} className="border-2 border-line px-3 py-1.5 font-semibold uppercase">
                {t}
              </li>
            ))}
          </ul>
        </section>

        <div className="w-full max-w-sm justify-self-center lg:justify-self-end">
          <form onSubmit={submit} className="card flex flex-col gap-4 p-7">
            <h2 className="text-[17px] font-semibold tracking-tight">
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
