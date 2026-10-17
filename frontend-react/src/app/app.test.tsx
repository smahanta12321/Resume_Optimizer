import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConnectionGate } from "@/layouts/ConnectionGate";
import { NAV } from "@/layouts/nav";
import { getToken } from "@/lib/session";
import { createMemoryRouter, RouterProvider } from "react-router";
import { mockApi, renderRoutes, testQueryClient } from "@/test/utils";
import { createQueryClient } from "./providers";
import { routes } from "./router";

afterEach(() => vi.unstubAllGlobals());

const dashboard = {
  profile: { state: "missing", version: null, is_sample: false, confirmed_at: null, experience: 0, projects: 0, skills: 0, warnings: 0 },
  role_profiles: [],
  jobs_total: 0,
  jobs_analyzed: 0,
  jobs_matched: 0,
  jobs_with_approved_resume: 0,
  jobs_exported: 0,
  versions_total: 0,
  applications_tracked: 0,
  recent_jobs: [],
  recent_versions: [],
  follow_ups_due: [],
  captures_waiting: 0,
};

function renderGate() {
  return render(
    <QueryClientProvider client={testQueryClient()}>
      <ConnectionGate>
        <p>app content</p>
      </ConnectionGate>
    </QueryClientProvider>,
  );
}

describe("ConnectionGate", () => {
  it("explains how to start the API when it isn't running", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    renderGate();
    expect(await screen.findByRole("heading", { name: "Start the local app" })).toBeInTheDocument();
    expect(screen.getByText("python -m src.api")).toBeInTheDocument();
    expect(screen.queryByText("app content")).toBeNull();
  });

  it("asks for the session token when the API rejects it, then connects", async () => {
    let tokenOk = false;
    mockApi({
      "GET /health": () => ({ json: { ok: true, app: "resume-optimizer-api", api_version: 1 } }),
      "GET /session": () =>
        tokenOk ? { json: { ok: true } } : { status: 401, json: { error: { code: "session_token_invalid", message: "Session token missing or wrong." } } },
    });
    renderGate();
    expect(await screen.findByRole("heading", { name: "Connect this tab" })).toBeInTheDocument();
    tokenOk = true;
    await userEvent.type(screen.getByLabelText("Session token"), "tok-123");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("app content")).toBeInTheDocument();
    expect(getToken()).toBe("tok-123");
  });
});

describe("session expiry with the app's real query client", () => {
  const unauthorized = { status: 401, json: { error: { code: "session_token_invalid", message: "Session token missing or wrong." } } };

  it("asks to reconnect without retrying the rejected token in a loop", async () => {
    const api = mockApi({
      "GET /health": () => ({ json: { ok: true, app: "resume-optimizer-api", api_version: 1 } }),
      "GET /session": () => unauthorized,
    });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ConnectionGate>
          <p>app content</p>
        </ConnectionGate>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "Connect this tab" })).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 200));
    expect(api.calls.filter((c) => c.path === "/session").length).toBe(1);
  });

  it("returns to the connect screen when the API restarts with a new token", async () => {
    let restarted = false;
    mockApi({
      "GET /health": () => ({ json: { ok: true, app: "resume-optimizer-api", api_version: 1 } }),
      "GET /session": () => (restarted ? unauthorized : { json: { ok: true } }),
      "GET /dashboard": () => (restarted ? unauthorized : { json: dashboard }),
    });
    const client = createQueryClient();
    const router = createMemoryRouter(routes, { initialEntries: ["/"] });
    render(
      <QueryClientProvider client={client}>
        <ConnectionGate>
          <RouterProvider router={router} />
        </ConnectionGate>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "Get started" })).toBeInTheDocument();
    restarted = true;
    await client.invalidateQueries({ queryKey: ["dashboard"] });
    expect(await screen.findByRole("heading", { name: "Connect this tab" })).toBeInTheDocument();
  });
});

describe("routing", () => {
  it("shows only supported screens in the navigation", async () => {
    mockApi({ "GET /dashboard": () => ({ json: dashboard }) });
    renderRoutes(routes, "/");
    const nav = await screen.findAllByRole("navigation", { name: "Main" });
    const labels = within(nav[0] as HTMLElement)
      .getAllByRole("link")
      .map((a) => a.textContent);
    expect(labels).toEqual(NAV.map((n) => n.label));
    expect(await screen.findByRole("heading", { name: "Get started" })).toBeInTheDocument();
  });

  it("renders a not-found page for unknown addresses", async () => {
    renderRoutes(routes, "/no/such/page");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});
