// Lab Record against the real server (M1.2): the same flow as record.spec.ts with no mock, so the Python server's
// REST, WebSocket, orchestrator and signed pulses are checked against the capture package end to end.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import type { Event } from "../packages/types/src/index";
import { E2E_DATA_DIR } from "./support/paths";

test("Lab Record runs a full light suite against the real server", async ({ page, request }) => {
  test.setTimeout(240_000);
  await page.goto("http://localhost:5173/record");
  await page.getByLabel("Person code").fill("P01");
  await page.getByLabel("Device code").fill("D99");
  await page.getByLabel("Genuine").check();
  await page.getByLabel("Consent reference").fill("C-E2E");
  await page.getByRole("button", { name: "Continue" }).click();
  const created = page.waitForResponse((r) => r.url().endsWith("/api/sessions") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Start" }).click();
  const { token } = await (await created).json();
  await expect(page.getByRole("heading", { name: "Recording saved" })).toBeVisible({ timeout: 100_000 });
  await expect(page.getByText("10 of 10 light pulses answered")).toBeVisible();
  const sessionId = (await page.locator("section[aria-label='Recording summary'] code").textContent())!;

  const unauthorised = await request.get(`http://localhost:5173/api/sessions/${sessionId}/events`);
  expect(unauthorised.status()).toBe(401); // scores never reach someone who only knows the session id
  const events: Event[] = (
    await (await request.get(`http://localhost:5173/api/sessions/${sessionId}/events`, { headers: { "X-Session-Token": token } })).json()
  ).events;
  expect(events.map((e) => e.seq)).toEqual(events.map((_, k) => k));
  expect(events[0]!.type).toBe("session.created");
  const stages = events.filter((e) => e.type === "stage.changed").map((e) => e.payload.stage);
  expect(stages).toEqual(["camera", "coach", "pulses"]);
  expect(events.filter((e) => e.type === "pulse.released")).toHaveLength(10);
  const acked = events.filter((e) => e.type === "pulse.acked");
  expect(acked).toHaveLength(10);
  expect(acked.every((e) => e.payload.ok === true)).toBe(true);
  expect(events.some((e) => e.type === "camera.details")).toBe(true);
  expect(events.filter((e) => e.type === "error")).toEqual([]);

  // The end screen analyses the bundle on the server and lists every check (SPEC 13.3 step 4).
  const results = page.getByRole("region", { name: "Results" });
  await expect(results.getByRole("heading", { name: "Results" })).toBeVisible({ timeout: 150_000 });
  await expect(results.getByRole("note")).toContainText("PROVISIONAL THRESHOLDS");
  await expect(results.getByLabel("Recording quality")).toContainText("fps");
  for (const family of ["Camera reality", "Optical response"]) await expect(results.getByRole("region", { name: family })).toBeVisible();
  await expect(results.getByRole("group", { name: "Mode-switch probe" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("record-results.png"), fullPage: true });

  const bundle = path.join(E2E_DATA_DIR, "sessions", sessionId);
  test.skip(!existsSync(bundle), "the server was reused from another run and writes elsewhere");
  const meta = JSON.parse(readFileSync(path.join(bundle, "meta.json"), "utf8"));
  expect(meta.label).toMatchObject({ person: "P01", device: "D99", kind: "genuine" });
  expect(meta.finalize.acks_ok).toBe(10);
  const pulses = readFileSync(path.join(bundle, "pulses.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
  expect(pulses).toHaveLength(10);
  expect(pulses.every((p) => p.ok && p.shown)).toBe(true);
  expect(readFileSync(path.join(bundle, "frames.jsonl"), "utf8").trim().split("\n").length).toBeGreaterThan(100);
});
