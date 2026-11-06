import { useCallback, useEffect, useState } from "react";
import ImportPage from "./components/ImportPage.jsx";
import RulesPage from "./components/RulesPage.jsx";
import { Toast } from "./components/ui.jsx";
import TransactionsPage from "./components/TransactionsPage.jsx";
import { api } from "./lib/api.js";

const TABS = [
  { id: "import", label: "Import" },
  { id: "transactions", label: "Transactions" },
  { id: "rules", label: "Rules" },
];

function tabFromHash() {
  const id = window.location.hash.replace("#", "");
  return TABS.some((t) => t.id === id) ? id : "import";
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

  const notify = useCallback((message, tone = "info") => setToast({ message, tone, at: Date.now() }), []);
  const closeToast = useCallback(() => setToast(null), []);

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <h1 className="text-lg font-semibold tracking-tight">Statement Ledger</h1>
          <nav className="flex gap-1" aria-label="Sections">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                aria-current={tab === t.id ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  tab === t.id
                    ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          {health?.demo_mode && (
            <span className="ml-auto rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              Demo mode · synthetic data
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        {loadError && (
          <div className="card mb-4 border-red-300 text-sm text-red-700 dark:border-red-900 dark:text-red-300">
            Could not reach the API: {loadError}. Is the backend running on port 8000?
          </div>
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
        {tab === "transactions" && (
          <TransactionsPage accounts={accounts} categories={categories} initialAccountId={accountId} notify={notify} />
        )}
        {tab === "rules" && <RulesPage categories={categories} notify={notify} />}
      </main>

      {toast && <Toast key={toast.at} message={toast.message} tone={toast.tone} onClose={closeToast} />}
    </div>
  );
}
