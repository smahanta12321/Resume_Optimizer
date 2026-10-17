/**
 * The main workflow against the real backend: sample profile → import a job → confirm requirements →
 * match → generate → approve → export and download → track the application.
 * Fictional data only (the app's own sample profile and a made-up posting).
 */
import { expect, test } from "@playwright/test";
import { E2E_TOKEN, WEB_PORT } from "./constants";

const JD = `Fictional Corp is hiring a Data Engineer (fictional posting for testing).

Requirements
- 2+ years of experience building data pipelines
- Python, SQL and Docker

Nice to have
- Kubernetes`;

test("tailor, approve, export and track a resume end to end", async ({ page }) => {
  // Connect with the session token, as the link printed by `python -m src.api` does.
  await page.goto(`/#token=${E2E_TOKEN}`);
  await expect(page.getByRole("heading", { name: "Get started" })).toBeVisible();
  await expect(page).not.toHaveURL(/token=/);

  // 1. Master profile: load the fictional sample and confirm it.
  await page.getByRole("link", { name: "Master profile" }).first().click();
  await page.getByRole("button", { name: "Load fictional sample profile" }).click();
  await expect(page.getByText("You're viewing the fictional sample profile")).toBeVisible();
  await page.getByRole("button", { name: "Confirm profile" }).click();
  await expect(page.getByText(/Reviewed and confirmed/)).toBeVisible();

  // 2. Import a job by pasting it.
  await page.goto("/jobs/new");
  await page.getByLabel("Job description").fill(JD);
  await page.getByRole("button", { name: "Review pasted text" }).click();
  await page.getByLabel("Job title").fill("Data Engineer");
  await page.getByLabel("Company").fill("Fictional Corp");
  await page.getByRole("button", { name: "Save job" }).click();

  // 3. Analyze, confirm, and match.
  await page.getByRole("button", { name: "Analyze job description" }).click();
  await expect(page.getByText(/Draft: correct the details/)).toBeVisible();
  await page.getByRole("button", { name: "Confirm analysis" }).click();
  await expect(page.getByRole("tab", { name: /Match report/, selected: true })).toBeVisible();
  await page.getByRole("button", { name: "Run matching" }).click();
  await expect(page.getByText("Required coverage")).toBeVisible();
  await expect(page.getByText(/Match estimate, not an ATS score/)).toBeVisible();

  // 4. Tailor: generate a draft from evidence (no AI provider configured).
  await page.getByRole("link", { name: "Tailor resume" }).click();
  await expect(page.getByRole("button", { name: /Generate draft/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "Generate draft", exact: true }).click();
  await expect(page.getByRole("article", { name: "Resume preview" })).toBeVisible();

  // 5. Review checks and approve.
  await page.getByRole("tab", { name: /Checks & approval/ }).click();
  await page.getByLabel(/I have read this resume/).check();
  await page.getByRole("button", { name: "Approve this version" }).click();

  // 6. Export and download the real files.
  await expect(page.getByRole("tab", { name: /Export/, selected: true })).toBeVisible();
  await page.getByRole("button", { name: "Export DOCX and PDF" }).click();
  await expect(page.getByRole("heading", { name: "Export checks" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);

  // 7. Track the application with the approved version.
  await page.goto("/tracker");
  await page.getByRole("button", { name: /Update Data Engineer @ Fictional Corp/ }).click();
  await page.getByLabel("Status").last().selectOption("applied");
  await page.getByLabel("Resume used").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("cell", { name: "Applied" })).toBeVisible();

  // Dashboard reflects real counts.
  await page.goto("/");
  await expect(page.getByText("Applications tracked")).toBeVisible();
  await expect(page.getByRole("link", { name: /Applications tracked\s*1/ })).toBeVisible();
});

test("a wrong session token shows the connect screen, not broken pages", async ({ browser }) => {
  const page = await browser.newPage({ baseURL: `http://localhost:${WEB_PORT}` });
  await page.goto("/#token=wrong-token");
  await expect(page.getByRole("heading", { name: "Connect this tab" })).toBeVisible();
  await page.getByLabel("Session token").fill(E2E_TOKEN);
  await page.getByRole("button", { name: "Connect" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});
