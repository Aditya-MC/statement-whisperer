// Thin client for the FastAPI backend. Every function returns parsed JSON or throws ApiError.

const BASE = import.meta.env?.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** Turn FastAPI error bodies (string detail or a list of validation errors) into one message. */
export function errorMessage(body, status) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const where = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
        return where ? `${where}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return `Request failed (HTTP ${status})`;
}

export function toQuery(params = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

// Called when a request comes back 401 (session expired or signed out elsewhere), so the app
// can show the sign-in screen. Auth endpoints themselves are excluded.
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

async function request(path, { method = "GET", json, form, params } = {}, fetchImpl = fetch) {
  // Same-origin requests send the HttpOnly session cookie automatically.
  const init = { method, headers: {}, credentials: "same-origin" };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form !== undefined) {
    init.body = form; // browser sets the multipart boundary
  }
  const res = await fetchImpl(`${BASE}${path}${toQuery(params)}`, init);
  if (res.status === 204) return null;
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized && !path.startsWith("/auth/")) onUnauthorized();
    throw new ApiError(res.status, errorMessage(body, res.status), body);
  }
  return body;
}

function statementForm({ accountId, file, mapping }) {
  const form = new FormData();
  if (accountId !== undefined) form.set("account_id", String(accountId));
  form.set("file", file, file.name);
  if (mapping) form.set("mapping", JSON.stringify(mapping));
  return form;
}

export function createApi(fetchImpl = (...a) => fetch(...a)) {
  const call = (path, opts) => request(path, opts, fetchImpl);
  return {
    health: () => call("/health"),
    authStatus: () => call("/auth/status"),
    me: () => call("/auth/me"),
    signup: (body) => call("/auth/signup", { method: "POST", json: body }),
    login: (body) => call("/auth/login", { method: "POST", json: body }),
    logout: () => call("/auth/logout", { method: "POST" }),
    deleteMe: (password) => call("/auth/me", { method: "DELETE", json: { password } }),
    createInvite: (note) => call("/admin/invites", { method: "POST", json: { note: note || null } }),
    listInvites: () => call("/admin/invites"),
    listAccounts: () => call("/accounts"),
    createAccount: (body) => call("/accounts", { method: "POST", json: body }),
    listCategories: () => call("/categories"),
    createCategory: (body) => call("/categories", { method: "POST", json: body }),
    renameCategory: (id, name) => call(`/categories/${id}`, { method: "PATCH", json: { name } }),
    deleteCategory: (id) => call(`/categories/${id}`, { method: "DELETE" }),
    restoreCategories: () => call("/categories/restore", { method: "POST" }),
    listImports: (accountId) => call("/imports", { params: { account_id: accountId } }),
    getImport: (id) => call(`/imports/${id}`),
    uploadStatement: ({ accountId, file, mapping }) =>
      call("/imports", { method: "POST", form: statementForm({ accountId, file, mapping }) }),
    retryImport: ({ importId, file, mapping }) =>
      call(`/imports/${importId}/retry`, { method: "POST", form: statementForm({ file, mapping }) }),
    listTransactions: (params) => call("/transactions", { params }),
    updateTransaction: (id, body) => call(`/transactions/${id}`, { method: "PATCH", json: body }),
    recategorize: (body = {}) => call("/categorize", { method: "POST", json: body }),
    listRules: (source) => call("/merchant-rules", { params: { source } }),
    dashboard: (params) => call("/analytics/dashboard", { params }),
    deleteRule: (id) => call(`/merchant-rules/${id}`, { method: "DELETE" }),
  };
}

export const api = createApi();
