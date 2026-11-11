import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { categoryLabels } from "../lib/categories.js";
import CategoriesPanel from "./CategoriesPanel.jsx";
import { Badge } from "./ui.jsx";

const SOURCES = [
  { value: "", label: "All rules" },
  { value: "user", label: "Your corrections" },
  { value: "llm", label: "Learned from AI" },
  { value: "seed", label: "Built-in" },
];

/** Categories tab: the category tree (add/rename/delete your own) and the merchant rules. */
export default function RulesPage({ categories, notify, onCategoriesChanged }) {
  const labels = useMemo(() => categoryLabels(categories), [categories]);
  const [source, setSource] = useState("user");
  const [rules, setRules] = useState([]);

  const load = useCallback(() => {
    api.listRules(source || undefined).then(setRules).catch((e) => notify(e.message, "error"));
  }, [source, notify]);
  useEffect(load, [load]);

  async function remove(rule) {
    try {
      await api.deleteRule(rule.id);
      notify(`Removed rule “${rule.pattern}”. Existing transactions keep their category.`, "success");
      load();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <CategoriesPanel
        categories={categories}
        notify={notify}
        onChanged={() => {
          onCategoriesChanged();
          load(); // deleting a category also removes its rules
        }}
      />

      <section className="card">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <h2 className="text-[17px] font-semibold tracking-tight">Merchant rules</h2>
          <select className="input" value={source} onChange={(e) => setSource(e.target.value)}>
            {SOURCES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <p className="w-full text-sm text-ink-2">
            A rule matches when its words appear in the cleaned merchant name. Your corrections always win, then
            built-in hints and rules, then answers remembered from the AI.
          </p>
        </div>
        {rules.length === 0 ? (
          <p className="text-sm text-muted">No rules here yet. Change a category on the Transactions tab to create one.</p>
        ) : (
          <ul className="divide-y divide-line text-sm">
            {rules.map((r) => (
              <li key={r.id} className="flex items-center gap-3 py-2">
                <span className="font-mono">{r.pattern}</span>
                <span className="text-muted">→</span>
                <span>{labels.get(r.category_id) ?? `#${r.category_id}`}</span>
                <Badge>{r.source}</Badge>
                <button type="button" className="ml-auto text-xs text-muted hover:text-critical" onClick={() => remove(r)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
