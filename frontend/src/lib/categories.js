// Helpers for the two-level category tree returned by GET /api/categories.

/** Group leaf categories under their parent, sorted, for <optgroup> menus. */
export function groupCategories(categories) {
  const parents = categories.filter((c) => c.parent_id === null);
  return parents
    .map((p) => ({
      id: p.id,
      name: p.name,
      kind: p.kind,
      options: categories
        .filter((c) => c.parent_id === p.id)
        .map((c) => ({ id: c.id, name: c.name }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Map of id -> "Group › Name" (or just the name for top-level groups). */
export function categoryLabels(categories) {
  const byId = new Map(categories.map((c) => [c.id, c]));
  const labels = new Map();
  for (const c of categories) {
    const parent = c.parent_id === null ? null : byId.get(c.parent_id);
    labels.set(c.id, parent ? `${parent.name} › ${c.name}` : c.name);
  }
  return labels;
}

export const SOURCE_LABELS = {
  user: "You",
  rule: "Rule",
  cache: "Cached",
  llm: "AI",
};
