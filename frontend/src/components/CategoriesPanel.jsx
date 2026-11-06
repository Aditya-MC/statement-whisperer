import { useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { groupCategories } from "../lib/categories.js";
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

/**
 * The category tree. Built-in categories are fixed (code and seed rules refer to them);
 * your own can be renamed (click the name) or deleted.
 */
export default function CategoriesPanel({ categories, onChanged, notify }) {
  const groups = useMemo(() => groupCategories(categories), [categories]);
  const byId = useMemo(() => new Map(categories.map((c) => [c.id, c])), [categories]);
  const [adding, setAdding] = useState(null); // null | { groupId }

  async function remove(cat) {
    const what = cat.parent_id === null ? `the group “${cat.name}” and its categories` : `“${cat.name}”`;
    if (!window.confirm(`Delete ${what}? Its transactions become uncategorized and its merchant rules are removed.`)) return;
    try {
      const r = await api.deleteCategory(cat.id);
      notify(`Deleted. ${r.transactions_uncategorized} transaction(s) now uncategorized, ${r.rules_removed} rule(s) removed.`, "success");
      onChanged();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  return (
    <section className="card">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Categories</h2>
          <p className="mt-0.5 text-sm text-ink-2">
            Add your own categories; they appear everywhere, including the AI's list. Click a custom name to rename it.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={() => setAdding({ groupId: groups[0]?.id })}>
          ＋ New category
        </button>
      </div>

      <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
        {groups.map((g) => {
          const group = byId.get(g.id);
          return (
            <div key={g.id} className="flex flex-col gap-1.5">
              <div className="flex items-baseline gap-2 border-b border-line pb-1">
                <span className="text-sm font-semibold">
                  {group?.is_custom ? <EditableName category={group} onRenamed={onChanged} notify={notify} /> : g.name}
                </span>
                <span className="text-[11px] text-muted">{KIND_LABEL[g.kind]}</span>
                <div className="ml-auto flex gap-2 text-xs">
                  <button type="button" className="text-muted hover:text-ink" onClick={() => setAdding({ groupId: g.id })}>
                    ＋ Add
                  </button>
                  {group?.is_custom && (
                    <button type="button" className="text-muted hover:text-critical" onClick={() => remove(group)}>
                      Delete
                    </button>
                  )}
                </div>
              </div>
              <ul className="flex flex-col gap-0.5 text-sm">
                {g.options.map((o) => {
                  const cat = byId.get(o.id);
                  return (
                    <li key={o.id} className="group flex items-center gap-2 text-ink-2">
                      {cat?.is_custom ? <EditableName category={cat} onRenamed={onChanged} notify={notify} /> : o.name}
                      {cat?.is_custom && (
                        <>
                          <span className="rounded border border-line px-1 text-[10px] text-muted">custom</span>
                          <button
                            type="button"
                            className="ml-auto text-xs text-muted opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-critical"
                            onClick={() => remove(cat)}
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </li>
                  );
                })}
                {g.options.length === 0 && <li className="text-xs text-muted">No categories yet.</li>}
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
    </section>
  );
}
