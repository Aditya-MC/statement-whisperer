import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import ImportPage from "./components/ImportPage.jsx";
import RulesPage from "./components/RulesPage.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";
import TransactionsPage from "./components/TransactionsPage.jsx";
import { Toast } from "./components/ui.jsx";
import { api } from "./lib/api.js";

// Charts (Recharts) are only needed on the dashboard, so that code loads on demand.
const DashboardPage = lazy(() => import("./components/dashboard/DashboardPage.jsx"));

const TABS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "transactions", label: "Transactions" },
  { id: "import", label: "Import" },
  { id: "categories", label: "Categories" },
];

function tabFromHash() {
  const id = window.location.hash.replace("#", "");
  if (id === "rules") return "categories"; // old bookmark
  return TABS.some((t) => t.id === id) ? id : "dashboard";
}

export default function App() {
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

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-line bg-page/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
          <h1 className="text-[15px] font-semibold tracking-tight">Statement Whisperer</h1>
          <nav className="flex gap-1" aria-label="Sections">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => {
                  if (t.id === "transactions") setDrill(null);
                  setTab(t.id);
                }}
                aria-current={tab === t.id ? "page" : undefined}
                className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
                  tab === t.id ? "bg-surface-2 font-medium text-ink" : "text-muted hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {health?.demo_mode && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-0.5 text-xs text-ink-2">
                <span aria-hidden="true" className="size-2 rounded-full bg-[#fab219]" />
                Demo · synthetic data
              </span>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        {loadError && (
          <div className="card mb-4 border-critical text-sm text-critical">
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
      </main>

      {toast && <Toast key={toast.at} message={toast.message} tone={toast.tone} onClose={closeToast} />}
    </div>
  );
}
