import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import AccountPage from "./components/AccountPage.jsx";
import AuthPage from "./components/AuthPage.jsx";
import ImportPage from "./components/ImportPage.jsx";
import PrivacyPage from "./components/PrivacyPage.jsx";
import RulesPage from "./components/RulesPage.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";
import TransactionsPage from "./components/TransactionsPage.jsx";
import { IconDashboard, IconList, IconPlus, IconTag, IconUpload } from "./components/icons.jsx";
import { PageHeader, Toast } from "./components/ui.jsx";
import { api, setUnauthorizedHandler } from "./lib/api.js";

// Charts (Recharts) are only needed on the dashboard, so that code loads on demand.
const DashboardPage = lazy(() => import("./components/dashboard/DashboardPage.jsx"));

const TABS = [
  { id: "dashboard", label: "Overview", icon: IconDashboard, subtitle: "Where your money came from and where it went." },
  { id: "transactions", label: "Transactions", icon: IconList, subtitle: "Every imported row, searchable and editable." },
  { id: "import", label: "Import", icon: IconUpload, subtitle: "Add a bank statement. The file is read in memory and never stored." },
  { id: "categories", label: "Categories", icon: IconTag, subtitle: "Your categories and the merchant rules that fill them." },
  { id: "account", label: "Account", hidden: true, subtitle: "Your login, invites and data." }, // opened from the avatar
  { id: "privacy", label: "Privacy", hidden: true },
];

function tabFromHash() {
  const id = window.location.hash.replace("#", "");
  if (id === "rules") return "categories"; // old bookmark
  return TABS.some((t) => t.id === id) ? id : "dashboard";
}

/** Decides between the sign-in screen and the app. */
export default function App() {
  // loading | signed_out | signed_in
  const [state, setState] = useState({ phase: "loading", user: null, firstRun: false, error: null });
  const [aiEnabled, setAiEnabled] = useState(false);

  const check = useCallback(async () => {
    try {
      const status = await api.authStatus();
      setAiEnabled(status.ai_enabled);
      try {
        const user = await api.me();
        setState({ phase: "signed_in", user, firstRun: false, error: null });
      } catch {
        setState({ phase: "signed_out", user: null, firstRun: !status.has_users, error: null });
      }
    } catch (e) {
      setState({ phase: "signed_out", user: null, firstRun: false, error: e.message });
    }
  }, []);

  useEffect(() => {
    check();
    // A 401 anywhere (expired session, signed out in another tab) returns to sign-in.
    setUnauthorizedHandler(() => setState((s) => ({ ...s, phase: "signed_out", user: null })));
    return () => setUnauthorizedHandler(null);
  }, [check]);

  if (state.phase === "loading") return null;
  if (state.phase === "signed_out") {
    return (
      <>
        {state.error && (
          <p className="bg-critical px-4 py-2 text-center text-sm text-white">
            Could not reach the server: {state.error}
          </p>
        )}
        <AuthPage
          firstRun={state.firstRun}
          aiEnabled={aiEnabled}
          onSignedIn={(user) => setState({ phase: "signed_in", user, firstRun: false, error: null })}
        />
      </>
    );
  }
  const signOut = async () => {
    try {
      await api.logout();
    } finally {
      window.location.hash = "";
      setState({ phase: "signed_out", user: null, firstRun: false, error: null });
    }
  };
  return (
    <LedgerApp key={state.user.id} user={state.user} aiEnabled={aiEnabled} onSignOut={signOut} onDeleted={check} />
  );
}

function LedgerApp({ user, aiEnabled, onSignOut, onDeleted }) {
  // The active tab lives in the URL hash so tabs can be bookmarked and survive reloads.
  const [tab, setTabState] = useState(tabFromHash);
  const setTab = useCallback((id) => {
    window.location.hash = id;
    setTabState(id);
  }, []);
  useEffect(() => {
    const onHash = () => setTabState(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const [accounts, setAccounts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [accountId, setAccountId] = useState(null);
  const [health, setHealth] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [toast, setToast] = useState(null);
  // Dashboard drill-down: filters handed to the Transactions page (remounted per drill-down).
  const [drill, setDrill] = useState(null);

  const loadAccounts = useCallback(async (selectId) => {
    const list = await api.listAccounts();
    setAccounts(list);
    setAccountId((current) => selectId ?? current ?? list[0]?.id ?? null);
  }, []);

  useEffect(() => {
    Promise.all([api.health(), api.listCategories(), loadAccounts()])
      .then(([h, cats]) => {
        setHealth(h);
        setCategories(cats);
      })
      .catch((e) => setLoadError(e.message));
  }, [loadAccounts]);

  const reloadCategories = useCallback(async () => setCategories(await api.listCategories()), []);
  const notify = useCallback((message, tone = "info") => setToast({ message, tone, at: Date.now() }), []);
  const closeToast = useCallback(() => setToast(null), []);
  const openTransactions = useCallback(
    (filters) => {
      setDrill({ ...filters, at: Date.now() });
      setTab("transactions");
    },
    [setTab],
  );

  const current = TABS.find((t) => t.id === tab);
  const go = (id) => {
    if (id === "transactions") setDrill(null);
    setTab(id);
  };
  const initial = (user.email?.[0] ?? "?").toUpperCase();

  return (
    <div className="min-h-screen">
      <NavRail tab={tab} go={go} initial={initial} email={user.email} />
      <MobileTopBar initial={initial} onAccount={() => setTab("account")} />
      <BottomTabs tab={tab} go={go} />

      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-4 pt-4 pb-32 md:pt-10 md:pr-8 md:pb-12 md:pl-[120px]">
        {current?.id !== "privacy" && (
          <PageHeader title={current?.label} subtitle={current?.subtitle}>
            {health?.demo_mode && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 text-xs text-ink-2 shadow-soft">
                <span aria-hidden="true" className="size-2 rounded-full bg-[#fab219]" />
                Demo · synthetic data
              </span>
            )}
            {tab !== "import" && tab !== "account" && (
              <button type="button" className="btn-primary" onClick={() => setTab("import")}>
                <IconPlus size={16} />
                Import
              </button>
            )}
          </PageHeader>
        )}
        {loadError && (
          <div className="card text-sm text-critical">
            Could not reach the API: {loadError}. Is the backend running on port 8000?
          </div>
        )}
        {tab === "dashboard" && (
          <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
            <DashboardPage
              accounts={accounts}
              categories={categories}
              onDrill={openTransactions}
              onImport={() => setTab("import")}
              notify={notify}
            />
          </Suspense>
        )}
        {tab === "transactions" && (
          <TransactionsPage
            key={drill?.at ?? "plain"}
            accounts={accounts}
            categories={categories}
            initialAccountId={accountId}
            preset={drill}
            notify={notify}
            onCategoriesChanged={reloadCategories}
          />
        )}
        {tab === "import" && (
          <ImportPage
            accounts={accounts}
            accountId={accountId}
            setAccountId={setAccountId}
            onAccountCreated={(id) => loadAccounts(id)}
            onViewTransactions={() => setTab("transactions")}
            notify={notify}
          />
        )}
        {tab === "categories" && (
          <RulesPage categories={categories} notify={notify} onCategoriesChanged={reloadCategories} />
        )}
        {tab === "account" && (
          <AccountPage
            user={user}
            onSignOut={onSignOut}
            onDeleted={onDeleted}
            onShowPrivacy={() => setTab("privacy")}
            notify={notify}
          />
        )}
        {tab === "privacy" && <PrivacyPage aiEnabled={aiEnabled} onBack={() => setTab("account")} />}
      </main>

      {toast && <Toast key={toast.at} message={toast.message} tone={toast.tone} onClose={closeToast} />}
    </div>
  );
}

const NAV_TABS = TABS.filter((t) => !t.hidden);

/** App mark: a pixel "S" key with a hard pixel shadow. Larger on the rail. */
function Logo({ onRail = true }) {
  return (
    <span
      aria-hidden="true"
      style={{ boxShadow: "var(--primary-glow)" }}
      className={`grid place-items-center bg-primary font-pixel font-bold text-on-primary ${
        onRail ? "size-11 text-[17px]" : "size-9 text-[15px]"
      }`}
    >
      S
    </span>
  );
}

/** Desktop: floating navy rail with round icon buttons; labels appear as hover tooltips. */
function NavRail({ tab, go, initial, email }) {
  const item = (active) =>
    `group relative grid size-11 place-items-center border-2 transition duration-200 ${
      active ? "border-rail-ink bg-rail-ink text-rail" : "border-transparent text-rail-muted hover:border-rail-muted hover:text-rail-ink"
    }`;
  const tip = (label) => (
    <span className="pointer-events-none absolute left-full ml-3 -translate-x-1 border-2 border-(--glass-border) bg-surface-solid px-3 py-1 font-pixel text-xs whitespace-nowrap text-ink uppercase opacity-0 transition duration-200 group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:translate-x-0 group-focus-visible:opacity-100">
      {label}
    </span>
  );
  return (
    <aside className="fixed top-4 bottom-4 left-4 z-40 hidden w-[76px] flex-col items-center rounded-[36px] border border-(--glass-border) bg-rail py-4 shadow-soft backdrop-blur-2xl md:flex">
      <Logo />
      <nav className="mt-8 flex flex-col gap-2" aria-label="Sections">
        {NAV_TABS.map((t) => (
          <button key={t.id} type="button" aria-label={t.label} aria-current={tab === t.id ? "page" : undefined} className={item(tab === t.id)} onClick={() => go(t.id)}>
            <t.icon />
            {tip(t.label)}
          </button>
        ))}
      </nav>
      <div className="mt-auto flex flex-col items-center gap-3">
        <ThemeToggle variant="cycle" className={item(false)} />
        <button
          type="button"
          aria-label="Account"
          title={email}
          onClick={() => go("account")}
          className={`grid size-11 place-items-center rounded-full text-sm font-semibold transition ${
            tab === "account" ? "bg-rail-ink text-rail" : "bg-rail-active text-rail-ink hover:bg-rail-ink hover:text-rail"
          }`}
        >
          {initial}
        </button>
      </div>
    </aside>
  );
}

/** Phone: app name with theme + account at the top… */
function MobileTopBar({ initial, onAccount }) {
  return (
    <div className="flex items-center gap-3 px-4 pt-4 md:hidden">
      <Logo onRail={false} />
      <span className="text-[15px] font-semibold tracking-tight">Statement Whisperer</span>
      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle variant="cycle" className="btn-icon" />
        <button type="button" aria-label="Account" onClick={onAccount} className="grid size-10 place-items-center rounded-full bg-primary text-sm font-semibold text-on-primary">
          {initial}
        </button>
      </div>
    </div>
  );
}

/** …and an iOS-style floating tab bar at the bottom. */
function BottomTabs({ tab, go }) {
  return (
    <nav
      aria-label="Sections"
      className="fixed inset-x-4 z-40 flex justify-around rounded-full border border-(--glass-border) bg-rail p-1.5 shadow-soft backdrop-blur-2xl md:hidden"
      style={{ bottom: "calc(1rem + env(safe-area-inset-bottom, 0px))" }}
    >
      {NAV_TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          aria-current={tab === t.id ? "page" : undefined}
          onClick={() => go(t.id)}
          className={`flex flex-1 flex-col items-center gap-0.5 rounded-full py-1.5 text-[10px] font-medium transition ${
            tab === t.id ? "bg-rail-active text-rail-ink" : "text-rail-muted"
          }`}
        >
          <t.icon size={20} />
          {t.label}
        </button>
      ))}
    </nav>
  );
}
