import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { E2E_DATA_DIR } from "./e2e/support/paths";

// Native separators and quotes: on Windows the command runs through cmd.exe.
const venvPython = `"${path.resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python")}"`;

// `make e2e` starts the server and both sites, or reuses ones already running locally.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: { trace: "retain-on-failure" },
  projects: [
    {
      name: "chromium-fake-camera",
      use: {
        ...devices["Desktop Chrome"],
        permissions: ["camera"],
        launchOptions: {
          // Chromium's built-in fake camera: a test pattern with no real face (CLAUDE.md test rules).
          args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
        },
      },
    },
  ],
  webServer: [
    {
      command: `${venvPython} -m uvicorn pulselens.api.main:app --host 127.0.0.1 --port 8000`,
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      env: { PULSE_DATA_DIR: E2E_DATA_DIR },
    },
    { command: "npm run dev -w @pulselens/lab", url: "http://localhost:5173", reuseExistingServer: !process.env.CI },
    { command: "npm run dev -w @pulselens/demo", url: "http://localhost:5174", reuseExistingServer: !process.env.CI },
  ],
});
