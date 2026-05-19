import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fetchStats, fetchFlags } from "@/lib/api";

const API_BASE = "http://localhost:8000/api";

function mockFetch(data: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => data,
  } as Response);
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch({}));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── fetchStats ─────────────────────────────────────────────────────────────────

describe("fetchStats", () => {
  it("constructs the correct URL", async () => {
    const spy = mockFetch({ total_companies_tracked: 5 });
    vi.stubGlobal("fetch", spy);

    await fetchStats();

    expect(spy).toHaveBeenCalledOnce();
    const [url] = spy.mock.calls[0] as [string];
    expect(url).toBe(`${API_BASE}/stats`);
  });

  it("throws when the response is not ok", async () => {
    vi.stubGlobal("fetch", mockFetch({}, false, 503));
    await expect(fetchStats()).rejects.toThrow("503");
  });
});

// ── fetchFlags ─────────────────────────────────────────────────────────────────

describe("fetchFlags", () => {
  it("builds correct URL with no params", async () => {
    const spy = mockFetch({ items: [], next_cursor: null, has_more: false, total_returned: 0 });
    vi.stubGlobal("fetch", spy);

    await fetchFlags();

    const [url] = spy.mock.calls[0] as [string];
    expect(url).toBe(`${API_BASE}/flags`);
  });

  it("builds query params correctly for single options", async () => {
    const spy = mockFetch({ items: [], next_cursor: null, has_more: false, total_returned: 0 });
    vi.stubGlobal("fetch", spy);

    await fetchFlags({ limit: 20, cursor: "abc123", sort: "detected_at_desc" });

    const [url] = spy.mock.calls[0] as [string];
    const parsed = new URL(url);
    expect(parsed.searchParams.get("limit")).toBe("20");
    expect(parsed.searchParams.get("cursor")).toBe("abc123");
    expect(parsed.searchParams.get("sort")).toBe("detected_at_desc");
  });

  it("handles severity array by joining with commas", async () => {
    const spy = mockFetch({ items: [], next_cursor: null, has_more: false, total_returned: 0 });
    vi.stubGlobal("fetch", spy);

    await fetchFlags({ severity: ["critical", "elevated"] });

    const [url] = spy.mock.calls[0] as [string];
    const parsed = new URL(url);
    expect(parsed.searchParams.get("severity")).toBe("critical,elevated");
  });

  it("handles single severity in array", async () => {
    const spy = mockFetch({ items: [], next_cursor: null, has_more: false, total_returned: 0 });
    vi.stubGlobal("fetch", spy);

    await fetchFlags({ severity: ["watch"] });

    const [url] = spy.mock.calls[0] as [string];
    const parsed = new URL(url);
    expect(parsed.searchParams.get("severity")).toBe("watch");
  });

  it("throws when response is not ok", async () => {
    vi.stubGlobal("fetch", mockFetch({}, false, 500));
    await expect(fetchFlags()).rejects.toThrow("500");
  });
});

// ── MethodologyResponse shape ──────────────────────────────────────────────────

describe("MethodologyResponse type shape", () => {
  it("has top-level in_scope and out_of_scope arrays (not nested under scope)", async () => {
    const apiShape = {
      methodology_version: "v1.0",
      classifier_version: "v1.0-claude-haiku-4-5",
      eval_set_version: "v1.0",
      current_metrics: {
        total_cases: 38,
        precision: "1.000",
        recall: "1.000",
        f1: "1.000",
        accuracy: "1.000",
        last_run: "2026-05-17T00:00:00Z",
      },
      in_scope: ["10-K annual filings", "Auditor's report section"],
      out_of_scope: ["8-K filings"],
    };

    const spy = mockFetch(apiShape);
    vi.stubGlobal("fetch", spy);

    const { fetchMethodology } = await import("@/lib/api");
    const result = await fetchMethodology();

    // in_scope and out_of_scope are on the root — NOT nested under a 'scope' key
    expect(Array.isArray(result.in_scope)).toBe(true);
    expect(Array.isArray(result.out_of_scope)).toBe(true);
    expect(result.in_scope[0]).toBe("10-K annual filings");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((result as any).scope).toBeUndefined();

    // current_metrics replaces the old eval_metrics key
    expect(result.current_metrics).not.toBeNull();
    expect(result.current_metrics?.total_cases).toBe(38);
    expect(typeof result.current_metrics?.precision).toBe("string");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((result as any).eval_metrics).toBeUndefined();
  });
});
