import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const root = resolve(process.cwd(), "../..");
const dataRoot = resolve(root, "artifacts/e2e");

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: [["list"], ["html", { open: "never" }]],
  globalSetup: "./tests/setup.ts",
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python -m uvicorn retentionops.api:app --host 127.0.0.1 --port 8100",
      cwd: root,
      url: "http://127.0.0.1:8100/health",
      env: { RETENTIONOPS_ROOT: dataRoot },
      reuseExistingServer: false,
    },
    {
      command: "npm run start",
      url: "http://127.0.0.1:3100",
      env: {
        RETENTIONOPS_API_URL: "http://127.0.0.1:8100",
        NEXT_TELEMETRY_DISABLED: "1",
        PORT: "3100",
      },
      reuseExistingServer: false,
    },
  ],
});
