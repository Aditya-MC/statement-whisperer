import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { Field } from "./ui.jsx";

const NEW_GROUP = "__new_group__";
const KINDS = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer (not counted as income or spending)" },
];

/**
 * Small modal to add a category, either under an existing group or as a new group.
 * Calls onCreated(category) on success. Escape or clicking the backdrop cancels.
 */
export default function NewCategoryDialog({ groups, defaultGroupId, onCreated, onClose }) {
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState(defaultGroupId ?? groups[0]?.id ?? NEW_GROUP);
  const [kind, setKind] = useState("expense");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = groupId === NEW_GROUP ? { name, kind } : { name, parent_id: Number(groupId) };
      onCreated(await api.createCategory(body));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[15vh] backdrop-blur-sm" onMouseDown={onClose}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-category-title"
        onSubmit={submit}
        onMouseDown={(e) => e.stopPropagation()}
        className="flex w-full max-w-sm flex-col gap-4 rounded-3xl border border-line bg-surface-solid p-6 shadow-xl"
      >
        <h2 id="new-category-title" className="text-sm font-semibold">
          New category
        </h2>
        <Field label="Name">
          <input ref={inputRef} className="input" required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Pets" />
        </Field>
        <Field label="Group">
          <select className="input" value={groupId} onChange={(e) => setGroupId(e.target.value === NEW_GROUP ? NEW_GROUP : Number(e.target.value))}>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
            <option value={NEW_GROUP}>New group…</option>
          </select>
        </Field>
        {groupId === NEW_GROUP && (
          <Field label="Counts as" hint="Categories inside this group will count the same way.">
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </Field>
        )}
        {error && <p className="text-sm text-critical">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={busy || !name.trim()}>
            {busy ? "Adding…" : "Add category"}
          </button>
        </div>
      </form>
    </div>
  );
}
