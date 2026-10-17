import { afterEach, describe, expect, it, vi } from "vitest";
import { setToken } from "@/lib/session";
import { ApiError, buildUrl, errorMessage, isApiError, request, TOKEN_HEADER } from "./client";
import { jsonResponse } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("request", () => {
  it("returns parsed JSON and sends the session token", async () => {
    setToken("abc123");
    const fn = stubFetch(async () => jsonResponse(200, { ok: true }));
    await expect(request("/session")).resolves.toEqual({ ok: true });
    const init = fn.mock.calls[0]?.[1];
    expect((init?.headers as Record<string, string>)[TOKEN_HEADER]).toBe("abc123");
    expect(init?.credentials).toBe("omit");
  });

  it("sends JSON bodies with a content type", async () => {
    const fn = stubFetch(async () => jsonResponse(200, {}));
    await request("/jobs", { method: "POST", json: { text: "x" } });
    const init = fn.mock.calls[0]?.[1];
    expect(init?.body).toBe('{"text":"x"}');
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("resolves undefined for 204", async () => {
    stubFetch(async () => new Response(null, { status: 204 }));
    await expect(request("/jobs/1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("normalizes the API error shape", async () => {
    stubFetch(async () =>
      jsonResponse(409, { error: { code: "version_conflict", message: "The profile changed.", details: { current_version: 3 } } }),
    );
    const err = await request("/profile", { method: "PUT", json: {} }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(isApiError(err, "version_conflict")).toBe(true);
    expect((err as ApiError).status).toBe(409);
    expect((err as ApiError).details).toEqual({ current_version: 3 });
    expect(errorMessage(err)).toBe("The profile changed.");
  });

  it("exposes field errors from validation failures", async () => {
    stubFetch(async () =>
      jsonResponse(422, { error: { code: "invalid_request", message: "Some fields are invalid.", details: [{ loc: ["body", "text"], msg: "required" }] } }),
    );
    const err = (await request("/jobs").catch((e: unknown) => e)) as ApiError;
    expect(err.fieldErrors).toEqual([{ loc: ["body", "text"], msg: "required" }]);
  });

  it("gives a generic error for non-JSON failures instead of pretending success", async () => {
    stubFetch(async () => new Response("<html>Bad gateway</html>", { status: 502 }));
    const err = (await request("/jobs").catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("http_502");
  });

  it("turns network failures into a clear network_error", async () => {
    stubFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    const err = (await request("/health").catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("network_error");
    expect(err.message).toMatch(/python -m src\.api/);
  });

  it("rethrows aborts untouched so callers can ignore them", async () => {
    stubFetch(async () => {
      throw new DOMException("aborted", "AbortError");
    });
    const err = await request("/jobs/drafts/url").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(DOMException);
  });
});

describe("buildUrl", () => {
  it("repeats array params and skips empty values", () => {
    const url = new URL(buildUrl("/tracker", { status: ["saved", "applied"], search: "", due_only: undefined, x: false }));
    expect(url.searchParams.getAll("status")).toEqual(["saved", "applied"]);
    expect(url.searchParams.has("search")).toBe(false);
    expect(url.searchParams.has("due_only")).toBe(false);
    expect(url.searchParams.get("x")).toBe("false");
  });
});
