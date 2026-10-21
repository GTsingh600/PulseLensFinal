// Replay attack, local only: a recorded genuine session plays as the camera (brave-replay project), so the face
// in the video changes colour at the old session's flash times, not this one's. The light echo must not pass.
// Make the file first: `python scripts/bundle_to_y4m.py data/sessions/<id>` (a consenting person's session).
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { E2E_DATA_DIR, REPLAY_Y4M } from "./support/paths";

const python = path.resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");

test("a replayed recording does not pass the light echo", async ({ page }) => {
  test.skip(!existsSync(REPLAY_Y4M), `no ${REPLAY_Y4M}; see the comment at the top of this file`);
  test.setTimeout(180_000);
  await page.goto("http://localhost:5173/record");
  await page.getByLabel("Person code").fill("P01");
  await page.getByLabel("Device code").fill("D99");
  await page.getByLabel("Attack").check();
  await page.getByLabel("Attack tool").selectOption({ index: 1 });
  await page.getByLabel("Consent reference").fill("C-REPLAY");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("heading", { name: "Recording saved" })).toBeVisible({ timeout: 150_000 });
  const sessionId = (await page.locator("section[aria-label='Recording summary'] code").textContent())!;

  const bundle = path.join(E2E_DATA_DIR, "sessions", sessionId);
  test.skip(!existsSync(bundle), "the server was reused from another run and writes elsewhere");
  execFileSync(python, ["-m", "pulselens.cli", "analyze", bundle], { cwd: path.resolve("server"), stdio: "inherit" });
  const checks = JSON.parse(readFileSync(path.join(bundle, "analysis", "checks.json"), "utf8")).checks as {
    check_id: string;
    status: string;
    reason: string;
  }[];
  const light = checks.find((c) => c.check_id === "optical.light.delay")!;
  const faceNeck = checks.find((c) => c.check_id === "optical.face_neck")!;
  test.info().annotations.push(
    { type: "optical.light.delay", description: `${light.status}: ${light.reason}` },
    { type: "optical.face_neck", description: `${faceNeck.status}: ${faceNeck.reason}` },
  );
  expect(light.status).not.toBe("pass");
  expect(faceNeck.status).not.toBe("pass");
});
