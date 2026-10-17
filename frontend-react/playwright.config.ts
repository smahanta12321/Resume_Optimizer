/**
 * End-to-end tests against the REAL local API (python -m src.api) and the Vite dev server.
 * Each run uses a fresh, throwaway data folder (e2e/.data) and the fictional sample profile,
 * on ports that don't clash with a copy you may already be running.
 */
import { existsSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";
import { API_PORT, E2E_TOKEN, WEB_PORT } from "./e2e/constants";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");
const dataRoot = join(here, "e2e", ".data");
const venvPython = process.platform === "win32" ? join(repo, ".venv", "Scripts", "python.exe") : join(repo, ".venv", "bin", "python");
const python = process.env.PYTHON || (existsSync(venvPython) ? venvPython : "python");

// Fresh data every run; never the user's real data folder. Only in the main process: workers load this
// config too, and by then the API has the database open.
if (!process.env.TEST_WORKER_INDEX && !process.env.PW_REUSE_DATA) rmSync(dataRoot, { recursive: true, force: true });

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    acceptDownloads: true,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${python}" -m src.api`,
      cwd: repo,
      url: `http://127.0.0.1:${API_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        RESUME_OPTIMIZER_DATA_DIR: join(dataRoot, "data"),
        RESUME_OPTIMIZER_OUTPUT_DIR: join(dataRoot, "output"),
        RESUME_OPTIMIZER_API_PORT: String(API_PORT),
        RESUME_OPTIMIZER_API_TOKEN: E2E_TOKEN,
        RESUME_OPTIMIZER_API_ORIGINS: `http://localhost:${WEB_PORT}`,
        // Keep the run offline and deterministic: no URL fetches, no AI provider.
        RESUME_OPTIMIZER_LOCAL_ONLY: "on",
        RESUME_OPTIMIZER_LLM_PROVIDER: "none",
      },
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_API_BASE_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
