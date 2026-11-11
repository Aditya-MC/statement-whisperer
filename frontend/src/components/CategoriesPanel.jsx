import { useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { NEW_GROUP, groupCategories } from "../lib/categories.js";
import { ConfirmDialog } from "./Modal.jsx";
import NewCategoryDialog from "./NewCategoryDialog.jsx";

const KIND_LABEL = { expense: "Spending", income: "Income", transfer: "Transfer" };

function EditableName({ category, onRenamed, notify }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(category.name);

  async function save() {
    const name = value.trim();
    if (!name || name === category.name) return setEditing(false);
    try {
      await api.renameCategory(category.id, name);
      setEditing(false);
      onRenamed();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  if (!editing) {
    return (
      <button type="button" className="hover:underline" title="Rename" onClick={() => setEditing(true)}>
        {category.name}
      </button>
    );
  }
  return (
    <input
      autoFocus
      className="input !py-0.5 text-sm"
      value={value}
      maxLength={60}
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Enter") save();
        if (e.key === "Escape") {
          setValue(category.name);
          setEditing(false);
        }
      }}
    />
  );
}

/** Small square key button (add / delete) used on each group and category. */
function KeyButton({ label, onClick, danger, children }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={`grid size-6 shrink-0 place-items-center border-2 border-line text-[13px] leading-none font-bold text-muted transition hover:-translate-x-px hover:-translate-y-px hover:shadow-[2px_2px_0_0_var(--axis)] active:translate-0 active:shadow-none ${
        danger ? "hover:border-critical hover:bg-critical hover:text-surface-solid" : "hover:border-ink hover:bg-ink hover:text-page"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * The category tree. Every group and category can be added to or deleted. Your own categories
 * can also be renamed (click the name). Deleting a built-in one only hides it for you, and
 * "Restore built-ins" brings them all back.
 */
export default function CategoriesPanel({ categories, onChanged, notify }) {
  const groups = useMemo(() => groupCategories(categories), [categories]);
  const byId = useMemo(() => new Map(categories.map((c) => [c.id, c])), [categories]);
  const [adding, setAdding] = useState(null); // null | { groupId }
  const [deleting, setDeleting] = useState(null); // category waiting for confirmation
  const [busy, setBusy] = useState(false);

  async function remove(cat) {
    setBusy(true);
    try {
      const r = await api.deleteCategory(cat.id);
      notify(`Deleted. ${r.transactions_uncategorized} transaction(s) now uncategorized, ${r.rules_removed} rule(s) removed.`, "success");
      setDeleting(null);
      onChanged();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function restore() {
    try {
      const r = await api.restoreCategories();
      notify(
        r.restored > 0 ? `Restored ${r.restored} built-in categor${r.restored === 1 ? "y" : "ies"}.` : "Nothing to restore.",
        "success",
      );
      if (r.restored > 0) onChanged();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  const deletingIsGroup = deleting?.parent_id === null;
  const deletingChildren = deletingIsGroup ? (groups.find((g) => g.id === deleting.id)?.options.length ?? 0) : 0;

  return (
    <section className="card">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[17px] font-semibold tracking-tight">Categories</h2>
          <p className="mt-0.5 text-sm text-ink-2">
            Add or delete any group or category; changes appear everywhere, including the AI's list. Click a custom name to rename it.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost" onClick={restore} title="Bring back built-in categories you deleted">
            Restore built-ins
          </button>
          <button type="button" className="btn-ghost" onClick={() => setAdding({ groupId: NEW_GROUP })}>
            ＋ New group
          </button>
          <button type="button" className="btn-primary" onClick={() => setAdding({ groupId: groups[0]?.id })}>
            ＋ New category
          </button>
        </div>
      </div>

      <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
        {groups.map((g) => {
          const group = byId.get(g.id);
          return (
            <div key={g.id} className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2 border-b-2 border-line pb-1.5">
                <span className="text-sm font-bold">
                  {group?.is_custom ? <EditableName category={group} onRenamed={onChanged} notify={notify} /> : g.name}
                </span>
                <span className="text-[11px] text-muted">{KIND_LABEL[g.kind]}</span>
                <div className="ml-auto flex gap-1.5">
                  <KeyButton label={`Add a category to ${g.name}`} onClick={() => setAdding({ groupId: g.id })}>
                    +
                  </KeyButton>
                  <KeyButton label={`Delete the ${g.name} group`} danger onClick={() => setDeleting(group)}>
                    ×
                  </KeyButton>
                </div>
              </div>
              <ul className="flex flex-col text-sm">
                {g.options.map((o) => {
                  const cat = byId.get(o.id);
                  return (
                    <li key={o.id} className="group flex min-h-8 items-center gap-2 px-1 text-ink-2 transition hover:bg-surface-2 hover:text-ink">
                      {cat?.is_custom ? <EditableName category={cat} onRenamed={onChanged} notify={notify} /> : o.name}
                      {cat?.is_custom && <span className="border border-line px-1 text-[10px] text-muted uppercase">custom</span>}
                      <span className="ml-auto opacity-0 transition group-hover:opacity-100 focus-within:opacity-100 max-md:opacity-100">
                        <KeyButton label={`Delete ${o.name}`} danger onClick={() => setDeleting(cat)}>
                          ×
                        </KeyButton>
                      </span>
                    </li>
                  );
                })}
                {g.options.length === 0 && <li className="px-1 text-xs text-muted">No categories yet.</li>}
              </ul>
            </div>
          );
        })}
      </div>

      {adding && (
        <NewCategoryDialog
          groups={groups}
          defaultGroupId={adding.groupId}
          onClose={() => setAdding(null)}
          onCreated={(cat) => {
            setAdding(null);
            notify(`Added “${cat.name}”.`, "success");
            onChanged();
          }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title={deletingIsGroup ? "Delete group" : "Delete category"}
          confirmLabel="Delete"
          busy={busy}
          onClose={() => setDeleting(null)}
          onConfirm={() => remove(deleting)}
        >
          <p>
            Delete <span className="font-bold text-ink">{deleting.name}</span>
            {deletingIsGroup && deletingChildren > 0 && ` and its ${deletingChildren} categor${deletingChildren === 1 ? "y" : "ies"}`}?
          </p>
          <p className="mt-2">
            Its transactions become uncategorized and your rules for it are removed.
            {!deleting.is_custom && " It's a built-in, so you can bring it back later with “Restore built-ins”."}
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}
