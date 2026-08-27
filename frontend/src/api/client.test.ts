/** API слоят: как се строят заявките и как се четат отказите на бекенда. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./client";

function mockFetch(status: number, body: unknown) {
  const spy = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

function urlOf(spy: ReturnType<typeof mockFetch>): URL {
  return new URL(spy.mock.calls[0][0] as string);
}

afterEach(() => vi.unstubAllGlobals());

describe("filters become query parameters", () => {
  it("skips empty values", async () => {
    const spy = mockFetch(200, { rows: [] });
    await api.listRankings("role-1", { q: "  ", outcome: "", min_score: null });

    const url = urlOf(spy);
    expect(url.pathname).toBe("/roles/role-1/rankings");
    expect(url.searchParams.has("q")).toBe(false);
    expect(url.searchParams.has("outcome")).toBe(false);
    expect(url.searchParams.has("min_score")).toBe(false);
  });

  it("passes the filters that are set", async () => {
    const spy = mockFetch(200, { rows: [] });
    await api.listRankings("role-1", {
      q: " Ivanova ",
      outcome: "pending",
      meets_minimum: false,
      min_score: 40,
      sort: "name_asc",
      ruleset_version: "2026.08.1",
    });

    const params = urlOf(spy).searchParams;
    expect(params.get("q")).toBe("Ivanova");
    expect(params.get("outcome")).toBe("pending");
    expect(params.get("meets_minimum")).toBe("false");
    expect(params.get("min_score")).toBe("40");
    expect(params.get("sort")).toBe("name_asc");
    expect(params.get("ruleset_version")).toBe("2026.08.1");
  });

  it("the decision goes out as PUT with the whole body", async () => {
    const spy = mockFetch(200, { id: "d1" });
    await api.putDecision("r1", {
      outcome: "advanced",
      decided_by: "ana",
      rationale: "covers everything",
    });

    const [, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
      outcome: "advanced",
      decided_by: "ana",
      rationale: "covers everything",
    });
  });
});

describe("errors keep the backend explanation", () => {
  it("passes a string detail through", async () => {
    mockFetch(409, { detail: "No active ruleset." });

    await expect(api.listRankings("role-1")).rejects.toMatchObject({
      status: 409,
      message: "No active ruleset.",
    });
  });

  it("folds the FastAPI validation list into a readable line", async () => {
    mockFetch(422, {
      detail: [{ loc: ["body", "rationale"], msg: "Field required" }],
    });

    await expect(
      api.putDecision("r1", { outcome: "rejected", decided_by: "ana", rationale: "" }),
    ).rejects.toThrow(/rationale: Field required/);
  });

  it("a network error differs from an HTTP error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed to fetch")));

    const error = await api.listRoles().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toMatch(/Is the backend running/);
  });
});
