/** Category picker with one <optgroup> per top-level group. */
export default function CategorySelect({ groups, value, onChange, disabled, allowAll = false, className = "" }) {
  return (
    <select
      className={`input w-full ${className}`}
      value={value ?? ""}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
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
    </select>
  );
}
