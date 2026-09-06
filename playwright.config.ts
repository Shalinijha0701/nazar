import path from "node:path";
import { defineConfig } from "@playwright/test";

const root = import.meta.dirname;
const python = path.resolve(root, ".venv", "Scripts", "python.exe");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    channel: "msedge",
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --port 8000`,
      cwd: path.resolve(root, "backend"),
      url: "http://localhost:8000/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_API_BASE: "http://localhost:8000",
        NEXT_PUBLIC_DEMO_TOKEN: "demo-token",
        NEXT_PUBLIC_POLL_MS: "1500",
      },
    },
  ],
});
