const NEW = "__new__";

/**
 * Category picker with one <optgroup> per top-level group. With `onRequestNew`, the last
 * option is "+ New category…", which calls it instead of changing the value.
 */
export default function CategorySelect({ groups, value, onChange, onRequestNew, disabled, allowAll = false, className = "" }) {
  return (
    <select
      className={`input w-full ${className}`}
      value={value ?? ""}
      disabled={disabled}
      onChange={(e) => {
        if (e.target.value === NEW) {
          onRequestNew();
          return;
        }
        onChange(e.target.value === "" ? null : Number(e.target.value));
      }}
    >
      <option value="">{allowAll ? "All categories" : "Uncategorized"}</option>
      {groups.map((g) => (
        <optgroup key={g.id} label={g.name}>
          {allowAll && <option value={g.id}>All {g.name}</option>}
          {g.options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </optgroup>
      ))}
      {onRequestNew && <option value={NEW}>＋ New category…</option>}
    </select>
  );
}
