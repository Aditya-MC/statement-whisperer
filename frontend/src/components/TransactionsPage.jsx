import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { SOURCE_LABELS, groupCategories } from "../lib/categories.js";
import { amountTone, formatDate, formatMoney } from "../lib/format.js";
import CategorySelect from "./CategorySelect.jsx";
import { Badge } from "./ui.jsx";

const PAGE_SIZE = 50;
// Server-side filtering and paging: the table only renders the current page.
const features = tableFeatures({});
const helper = createColumnHelper();
const SOURCE_TONES = { user: "emerald", rule: "sky", cache: "zinc", llm: "violet" };

function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function TransactionsPage({ accounts, categories, initialAccountId, notify }) {
  const groups = useMemo(() => groupCategories(categories), [categories]);
  const accountsById = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);
  const [filters, setFilters] = useState({
    account_id: initialAccountId ?? null,
    category_id: null,
    uncategorized: false,
    transfers: "all",
  });
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [busy, setBusy] = useState(false);

  const setFilter = (k) => (v) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setOffset(0);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listTransactions({
        account_id: filters.account_id,
        category_id: filters.category_id,
        uncategorized: filters.uncategorized,
        is_transfer: filters.transfers === "all" ? undefined : filters.transfers === "only",
        q,
        limit: PAGE_SIZE,
        offset,
      });
      setPage(data);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [filters, q, offset, notify]);

  useEffect(() => {
    load();
  }, [load]);

  const changeCategory = useCallback(
    async (txn, categoryId) => {
      if (categoryId == null) return;
      setSavingId(txn.id);
      try {
        const res = await api.updateTransaction(txn.id, { category_id: categoryId });
        setPage((p) => ({ ...p, items: p.items.map((t) => (t.id === txn.id ? res.transaction : t)) }));
        const merchant = txn.cleaned_merchant ?? "this merchant";
        notify(
          res.updated_similar > 0
            ? `Saved as a rule for ${merchant}; updated ${res.updated_similar} similar transaction(s).`
            : `Saved. Future ${merchant} transactions will use this category.`,
          "success",
        );
        if (res.updated_similar > 0) load();
      } catch (e) {
        notify(e.message, "error");
      } finally {
        setSavingId(null);
      }
    },
    [load, notify],
  );

  const unlinkTransfer = useCallback(
    async (txn) => {
      try {
        await api.updateTransaction(txn.id, { is_transfer: false });
        notify("Unlinked. Both sides were re-categorized.", "success");
        load();
      } catch (e) {
        notify(e.message, "error");
      }
    },
    [load, notify],
  );

  async function recategorize() {
    setBusy(true);
    try {
      const r = await api.recategorize({ account_id: filters.account_id, only_uncategorized: true });
      notify(
        r.llm_error
          ? `Categorized with rules only (${r.llm_error}). ${r.uncategorized} still uncategorized.`
          : `Processed ${r.processed}; ${r.llm_merchants} merchant(s) sent to AI; ${r.uncategorized} left.`,
        r.llm_error ? "info" : "success",
      );
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const showAccount = filters.account_id == null && accounts.length > 1;
  const columns = useMemo(
    () =>
      helper.columns([
        helper.accessor("date", {
          header: "Date",
          cell: (info) => <span className="whitespace-nowrap tabular-nums">{formatDate(info.getValue())}</span>,
        }),
        helper.display({
          id: "description",
          header: "Description",
          cell: ({ row }) => {
            const t = row.original;
            return (
              <div className="min-w-0">
                <div className="truncate font-medium">{t.cleaned_merchant ?? "—"}</div>
                <div className="truncate text-xs text-zinc-500" title={t.raw_narration}>
                  {t.raw_narration}
                </div>
                {showAccount && (
                  <div className="text-xs text-zinc-400">{accountsById.get(t.account_id)?.nickname}</div>
                )}
              </div>
            );
          },
        }),
        helper.accessor("amount", {
          header: () => <span className="block text-right">Amount</span>,
          cell: (info) => (
            <span className={`block text-right whitespace-nowrap tabular-nums ${amountTone(info.getValue())}`}>
              {formatMoney(info.getValue(), info.row.original.currency)}
            </span>
          ),
        }),
        helper.display({
          id: "category",
          header: "Category",
          cell: ({ row }) => {
            const t = row.original;
            return (
              <div className="flex min-w-52 flex-col gap-1">
                <CategorySelect
                  groups={groups}
                  value={t.category_id}
                  disabled={savingId === t.id}
                  onChange={(id) => changeCategory(t, id)}
                  className="!py-1"
                />
                <div className="flex flex-wrap items-center gap-1">
                  {t.category_source && (
                    <Badge tone={SOURCE_TONES[t.category_source]} title="How this category was chosen">
                      {SOURCE_LABELS[t.category_source]}
                    </Badge>
                  )}
                  {t.is_transfer && (
                    <>
                      <Badge tone="amber" title="Matched with an opposite transaction in another of your accounts">
                        Own transfer
                      </Badge>
                      <button type="button" className="text-[11px] text-zinc-500 underline" onClick={() => unlinkTransfer(t)}>
                        not a transfer?
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          },
        }),
      ]),
    [groups, savingId, changeCategory, unlinkTransfer, showAccount, accountsById],
  );

  const table = useTable({ features, columns, data: page.items, getRowId: (row) => String(row.id) });
  const pageNo = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(page.total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-4">
      <section className="card flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Account</span>
          <select
            className="input"
            value={filters.account_id ?? ""}
            onChange={(e) => setFilter("account_id")(e.target.value === "" ? null : Number(e.target.value))}
          >
            <option value="">All accounts</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nickname}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Search</span>
          <input
            className="input w-56"
            type="search"
            placeholder="Merchant or narration"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label className="flex w-56 flex-col gap-1 text-sm">
          <span className="font-medium">Category</span>
          <CategorySelect groups={groups} value={filters.category_id} onChange={setFilter("category_id")} allowAll />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Transfers</span>
          <select className="input" value={filters.transfers} onChange={(e) => setFilter("transfers")(e.target.value)}>
            <option value="all">Include</option>
            <option value="exclude">Exclude</option>
            <option value="only">Only transfers</option>
          </select>
        </label>
        <label className="flex items-center gap-2 pb-1.5 text-sm">
          <input type="checkbox" checked={filters.uncategorized} onChange={(e) => setFilter("uncategorized")(e.target.checked)} />
          Uncategorized only
        </label>
        <button type="button" className="btn-ghost ml-auto" onClick={recategorize} disabled={busy}>
          {busy ? "Categorizing…" : "Categorize uncategorized"}
        </button>
      </section>

      <section className="card overflow-x-auto p-0">
        <table className="w-full table-fixed text-sm">
          <colgroup>
            <col className="w-28" />
            <col />
            <col className="w-36" />
            <col className="w-64" />
          </colgroup>
          <thead className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => (
                  <th key={header.id} className="px-4 py-2.5 font-medium">
                    {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-zinc-100 align-top last:border-0 dark:border-zinc-800">
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-2.5">
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
            {!loading && page.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-zinc-500">
                  No transactions match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <div className="flex items-center justify-between text-sm text-zinc-600 dark:text-zinc-400">
        <span>
          {page.total} transaction{page.total === 1 ? "" : "s"}
          {loading && " · loading…"}
        </span>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            ← Prev
          </button>
          <span className="tabular-nums">
            {pageNo} / {pages}
          </span>
          <button
            type="button"
            className="btn-ghost"
            disabled={offset + PAGE_SIZE >= page.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}
