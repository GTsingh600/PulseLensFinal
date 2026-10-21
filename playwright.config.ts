import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { E2E_DATA_DIR, REPLAY_Y4M } from "./e2e/support/paths";

// Native separators and quotes: on Windows the command runs through cmd.exe.
const venvPython = `"${path.resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python")}"`;

// Chromium's built-in fake camera: a test pattern with no real face (CLAUDE.md test rules).
const fakeCamera = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"];

// The installed Brave (Chromium-based), driven headed: `npx playwright test --project=brave-fake-camera`.
// BRAVE_PATH overrides the default install location.
const bravePath =
  process.env.BRAVE_PATH ??
  (process.platform === "win32"
    ? "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"
    : process.platform === "darwin"
      ? "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
      : "/usr/bin/brave-browser");

// `make e2e` starts the server and both sites, or reuses ones already running locally.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: { trace: "retain-on-failure" },
  projects: [
    {
      name: "chromium-fake-camera",
      testIgnore: /replay\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        permissions: ["camera"],
        launchOptions: { args: fakeCamera },
      },
    },
    {
      name: "brave-fake-camera",
      testIgnore: /replay\.spec\.ts/,
      use: {
        // Brave's own user agent, not the Chrome preset's, so the Camera card reports the real browser.
        viewport: { width: 1280, height: 720 },
        permissions: ["camera"],
        headless: false,
        launchOptions: { executablePath: bravePath, args: fakeCamera },
      },
    },
    {
      // The installed Google Chrome, headed: what most customers run. No download (channel uses the system install).
      name: "chrome-fake-camera",
      testIgnore: /replay\.spec\.ts/,
      use: {
        viewport: { width: 1280, height: 720 },
        permissions: ["camera"],
        headless: false,
        channel: "chrome",
        launchOptions: { args: fakeCamera },
      },
    },
    {
      // Local replay attack: a recorded session as the camera (scripts/bundle_to_y4m.py). Skipped without the file.
      name: "brave-replay",
      testMatch: /replay\.spec\.ts/,
      use: {
        viewport: { width: 1280, height: 720 },
        permissions: ["camera"],
        headless: false,
        launchOptions: { executablePath: bravePath, args: [...fakeCamera, `--use-file-for-fake-video-capture=${REPLAY_Y4M}`] },
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
