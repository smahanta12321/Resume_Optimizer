/**
 * Test helpers. `mockApi` stubs `fetch` for isolated component tests only: the running app never
 * falls back to fake data.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { vi } from "vitest";

type Handler = (body: unknown, url: URL) => { status?: number; json?: unknown; text?: string };

export function jsonResponse(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Routes keyed "METHOD /path" (path after /api/v1). Unmatched requests fail the test loudly. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown; headers: Headers }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
    calls.push({ method, path, body, headers: new Headers(init?.headers) });
    const handler = routes[`${method} ${path}`];
    if (!handler) throw new Error(`Unmocked request: ${method} ${path}`);
    const out = handler(body, url);
    if (out.status === 204) return new Response(null, { status: 204 });
    return out.text !== undefined ? new Response(out.text, { status: out.status ?? 200 }) : jsonResponse(out.status ?? 200, out.json);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function testQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
}

export function renderRoutes(routes: RouteObject[], initialPath = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  const client = testQueryClient();
  const utils = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...utils, router, client };
}

export function renderPage(element: ReactNode, path = "/", initialPath = path) {
  return renderRoutes([{ path, element }], initialPath);
}
