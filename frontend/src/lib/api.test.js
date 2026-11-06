import { describe, expect, it } from "vitest";
import { ApiError, createApi, errorMessage, toQuery } from "./api.js";

function fakeFetch(status, body) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: status >= 200 && status < 300,
      status,
      text: async () => (body === undefined ? "" : JSON.stringify(body)),
    };
  };
  fn.calls = calls;
  return fn;
}

describe("toQuery", () => {
  it("drops empty values and false flags", () => {
    expect(toQuery({ a: 1, b: "", c: null, d: undefined, e: false, f: true })).toBe("?a=1&f=true");
    expect(toQuery({})).toBe("");
  });
});

describe("errorMessage", () => {
  it("handles string and validation-list details", () => {
    expect(errorMessage({ detail: "Nope" }, 400)).toBe("Nope");
    expect(
      errorMessage({ detail: [{ loc: ["body", "currency"], msg: "bad code" }] }, 422),
    ).toBe("currency: bad code");
    expect(errorMessage(null, 500)).toBe("Request failed (HTTP 500)");
  });
});

describe("createApi", () => {
  it("sends multipart uploads with the mapping as JSON", async () => {
    const fetch = fakeFetch(201, { id: 7, status: "completed" });
    const api = createApi(fetch);
    const file = new File(["Date,Amount\n"], "jan.csv", { type: "text/csv" });
    const res = await api.uploadStatement({ accountId: 3, file, mapping: { currency: "INR" } });

    expect(res.id).toBe(7);
    const { url, init } = fetch.calls[0];
    expect(url).toBe("/api/imports");
    expect(init.method).toBe("POST");
    expect(init.body.get("account_id")).toBe("3");
    expect(init.body.get("file").name).toBe("jan.csv");
    expect(JSON.parse(init.body.get("mapping"))).toEqual({ currency: "INR" });
  });

  it("sends JSON for PATCH and builds query strings", async () => {
    const fetch = fakeFetch(200, { total: 0, items: [] });
    const api = createApi(fetch);
    await api.listTransactions({ account_id: 1, q: "coffee", uncategorized: false });
    expect(fetch.calls[0].url).toBe("/api/transactions?account_id=1&q=coffee");

    await api.updateTransaction(5, { category_id: 9 });
    const { url, init } = fetch.calls[1];
    expect(url).toBe("/api/transactions/5");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ category_id: 9 });
  });

  it("throws ApiError with status and body on failure", async () => {
    const api = createApi(fakeFetch(409, { detail: "Already imported", existing_import_id: 4 }));
    const file = new File(["x"], "a.csv");
    await expect(api.uploadStatement({ accountId: 1, file })).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "Already imported",
      body: { existing_import_id: 4 },
    });
    expect(new ApiError(1, "m")).toBeInstanceOf(Error);
  });

  it("returns null for 204 responses", async () => {
    const api = createApi(fakeFetch(204));
    expect(await api.deleteRule(3)).toBeNull();
  });
});
