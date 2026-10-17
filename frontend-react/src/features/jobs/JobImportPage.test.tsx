import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderRoutes } from "@/test/utils";
import { JobImportPage } from "./JobImportPage";

afterEach(() => vi.unstubAllGlobals());

const JD = "Fictional Corp is hiring a Data Engineer. Requirements: Python, SQL and Docker.";
const draft = {
  text: JD,
  method: "paste",
  text_notes: ["The text is short (80 characters). It may be incomplete."],
  source_notes: [],
  title: "",
  company: "",
  location: "",
  source_url: "",
  source_label: "",
  suggested_platform: "other",
  capture_id: null,
};
const savedJob = { id: "job-existing", title: "Data Engineer", company: "Fictional Corp", imported_at: "2026-10-01T10:00:00Z" };

function setup() {
  return renderRoutes(
    [
      { path: "/jobs/new", element: <JobImportPage /> },
      { path: "/jobs/:jobId", element: <p>job detail page</p> },
    ],
    "/jobs/new",
  );
}

describe("JobImportPage", () => {
  it("reviews pasted text, then saves after a duplicate decision", async () => {
    const api = mockApi({
      "POST /jobs/drafts/text": () => ({ json: draft }),
      "POST /jobs": (body) =>
        (body as { on_duplicate: string }).on_duplicate === "check"
          ? {
              status: 409,
              json: { error: { code: "duplicate", message: "Looks like a saved job.", details: { duplicates: [{ job: savedJob, reason: "same company, title and text" }] } } },
            }
          : { status: 201, json: { job: { id: "job-existing" }, merged: true } },
    });
    setup();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Job description"), JD);
    await user.click(screen.getByRole("button", { name: "Review pasted text" }));

    expect(await screen.findByText(/2\. Review and save/)).toBeInTheDocument();
    expect(screen.getByText(/The text is short/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Job title"), "Data Engineer");
    await user.click(screen.getByRole("button", { name: "Save job" }));

    expect(await screen.findByText(/2\. Possible duplicate/)).toBeInTheDocument();
    expect(screen.getByText(/same company, title and text/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Update the saved job with this import" }));

    expect(await screen.findByText("job detail page")).toBeInTheDocument();
    const merge = api.calls.find((c) => c.method === "POST" && c.path === "/jobs" && (c.body as { on_duplicate: string }).on_duplicate === "merge");
    expect(merge?.body).toMatchObject({ title: "Data Engineer", method: "paste", merge_into_id: "job-existing", text: JD });
  });

  it("validates the review form before calling the API", async () => {
    const api = mockApi({ "POST /jobs/drafts/text": () => ({ json: draft }) });
    setup();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Job description"), JD);
    await user.click(screen.getByRole("button", { name: "Review pasted text" }));
    const url = await screen.findByLabelText(/Source URL/);
    await user.type(url, "not a url");
    await user.click(screen.getByRole("button", { name: "Save job" }));
    expect(await screen.findByText(/Enter a full http\(s\) URL/)).toBeInTheDocument();
    expect(api.calls.some((c) => c.path === "/jobs")).toBe(false);
  });

  it("shows the API's reason and a paste fallback when URL import fails", async () => {
    mockApi({
      "GET /settings": () => ({ json: { values: { url_import_enabled: true, local_only: false } } }),
      "POST /jobs/drafts/url": () => ({
        status: 422,
        json: { error: { code: "url_import_failed", message: "This page needs sign-in. Paste the job description instead.", details: { reason: "login_required" } } },
      }),
    });
    setup();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /From URL/ }));
    await user.type(await screen.findByLabelText("Job page URL"), "https://www.linkedin.com/jobs/view/1");
    await user.click(screen.getByRole("button", { name: "Fetch page" }));
    expect(await screen.findByText(/needs sign-in/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Paste instead" }));
    expect(screen.getByLabelText("Job description")).toBeInTheDocument();
  });

  it("explains when URL import is turned off", async () => {
    mockApi({ "GET /settings": () => ({ json: { values: { url_import_enabled: false, local_only: true } } }) });
    setup();
    await userEvent.click(screen.getByRole("tab", { name: /From URL/ }));
    expect(await screen.findByText(/Local-only mode is on/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Job page URL")).toBeNull();
  });
});
