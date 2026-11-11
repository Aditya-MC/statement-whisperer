import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { SOURCE_LABELS, groupCategories } from "../lib/categories.js";
import { amountTone, formatDate, formatMoney } from "../lib/format.js";
import CategorySelect from "./CategorySelect.jsx";
import NewCategoryDialog from "./NewCategoryDialog.jsx";
import { IconSearch } from "./icons.jsx";
import { Badge } from "./ui.jsx";

const PAGE_SIZE = 50;
// Server-side filtering and paging: the table only renders the current page.
const features = tableFeatures({});
const helper = createColumnHelper();

function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/**
 * `preset` comes from a dashboard drill-down ({category_id, date_from, date_to, q, uncategorized,
 * account_id}). The parent remounts this page (via `key`) for each new drill-down.
 */
export default function TransactionsPage({ accounts, categories, initialAccountId, preset, notify, onCategoriesChanged }) {
  // Row whose "+ New category…" was picked; the new category is applied to it once created.
  const [newCategoryFor, setNewCategoryFor] = useState(null);
  const groups = useMemo(() => groupCategories(categories), [categories]);
  const accountsById = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);
  const [filters, setFilters] = useState(() => ({
    account_id: preset?.account_id !== undefined ? preset.account_id : (initialAccountId ?? null),
    category_id: preset?.category_id ?? null,
    uncategorized: preset?.uncategorized ?? false,
    transfers: "all",
    date_from: preset?.date_from ?? null,
    date_to: preset?.date_to ?? null,
  }));
  const [search, setSearch] = useState(preset?.q ?? "");
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
        date_from: filters.date_from,
        date_to: filters.date_to,
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
                <div className="truncate text-xs text-muted" title={t.raw_narration}>
                  {t.raw_narration}
                </div>
                {showAccount && (
                  <div className="text-xs text-muted">{accountsById.get(t.account_id)?.nickname}</div>
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
                  onRequestNew={() => setNewCategoryFor(t)}
                  className="!py-1"
                />
                <div className="flex flex-wrap items-center gap-1">
                  {t.category_source && (
                    <Badge title="How this category was chosen">
                      {SOURCE_LABELS[t.category_source]}
                    </Badge>
                  )}
                  {t.is_transfer && (
                    <>
                      <Badge title="Matched with an opposite transaction in another of your accounts">
                        Own transfer
                      </Badge>
                      <button type="button" className="text-[11px] text-muted underline" onClick={() => unlinkTransfer(t)}>
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
      <section className="flex flex-wrap items-center gap-2">
        <label className="relative w-full sm:w-64">
          <span className="sr-only">Search</span>
          <IconSearch size={16} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted" />
          <input
            className="input w-full pl-9"
            type="search"
            placeholder="Search merchant or narration"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <select
          aria-label="Account"
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
        <label className="w-52">
          <span className="sr-only">Category</span>
          <CategorySelect groups={groups} value={filters.category_id} onChange={setFilter("category_id")} allowAll />
        </label>
        <select aria-label="Transfers" className="input" value={filters.transfers} onChange={(e) => setFilter("transfers")(e.target.value)}>
          <option value="all">Transfers included</option>
          <option value="exclude">Transfers excluded</option>
          <option value="only">Only transfers</option>
        </select>
        <label
          className={`inline-flex cursor-pointer items-center gap-2 rounded-full border px-3.5 py-2 text-sm transition ${
            filters.uncategorized ? "border-primary bg-primary text-on-primary" : "border-line bg-surface text-ink-2 hover:bg-surface-2"
          }`}
        >
          <input type="checkbox" className="sr-only" checked={filters.uncategorized} onChange={(e) => setFilter("uncategorized")(e.target.checked)} />
          Uncategorized only
        </label>
        {(filters.date_from || filters.date_to) && (
          <span className="inline-flex items-center gap-2 rounded-full bg-surface-2 px-3 py-2 text-xs text-ink-2">
            {filters.date_from ? formatDate(filters.date_from) : "Start"} – {filters.date_to ? formatDate(filters.date_to) : "today"}
            <button
              type="button"
              aria-label="Clear date range"
              className="text-muted hover:text-ink"
              onClick={() => {
                setFilters((f) => ({ ...f, date_from: null, date_to: null }));
                setOffset(0);
              }}
            >
              ✕
            </button>
          </span>
        )}
        <button type="button" className="btn-ghost ml-auto" onClick={recategorize} disabled={busy}>
          {busy ? "Categorizing…" : "Categorize uncategorized"}
        </button>
      </section>

      <section className="card overflow-x-auto p-0">
        <table className="w-full min-w-[760px] table-fixed text-sm">
          <colgroup>
            <col className="w-28" />
            <col />
            <col className="w-36" />
            <col className="w-64" />
          </colgroup>
          <thead className="border-b border-line text-left text-xs text-muted">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => (
                  <th key={header.id} className="px-5 py-3.5 font-medium">
                    {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-line align-top transition-colors last:border-0 hover:bg-surface-2/60">
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className="px-5 py-3">
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
            {!loading && page.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-muted">
                  No transactions match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <div className="flex items-center justify-between text-sm text-ink-2">
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

      {newCategoryFor && (
        <NewCategoryDialog
          groups={groups}
          defaultGroupId={categories.find((c) => c.id === newCategoryFor.category_id)?.parent_id}
          onClose={() => setNewCategoryFor(null)}
          onCreated={async (cat) => {
            const txn = newCategoryFor;
            setNewCategoryFor(null);
            await onCategoriesChanged?.();
            changeCategory(txn, cat.id);
          }}
        />
      )}
    </div>
  );
}
