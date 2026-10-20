// M1.6 acceptance: e2e records a labelled bundle, and the explainer text matches EXPLAINERS.md.
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { parseExplainers } from "../packages/explain/src/parse";
import { MockServer } from "./support/mock-server";

const ex = parseExplainers(readFileSync(path.join(import.meta.dirname, "../docs/EXPLAINERS.md"), "utf8"));
const text = (key: string, field: "title" | "what" | "why" | "text") => {
  const value = ex[key]?.[field];
  if (!value) throw new Error(`EXPLAINERS.md has no ${field} for ${key}`);
  return value;
};

test("Lab Record uploads a labelled bundle and explains every stage in EXPLAINERS.md words", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const server = new MockServer(testInfo.outputPath("bundles"));
  await server.install(page);
  await page.goto("http://localhost:5173/record");

  await test.step("operator form", async () => {
    await page.getByLabel("Person code").fill("P07");
    await page.getByLabel("Device code").fill("D02");
    await page.getByLabel("Light").selectOption("dim");
    await page.getByLabel("Genuine").check();
    await page.getByLabel("Consent reference").fill("C-2026-07");
    await page.getByRole("button", { name: "Continue" }).click();
  });

  await page.getByRole("button", { name: "Start" }).click();
  const panel = page.getByRole("region", { name: "Stage explanation" });

  for (const stage of ["stage.camera", "stage.coach", "stage.pulses"]) {
    await test.step(`${stage} explainer`, async () => {
      await expect(panel.getByRole("heading")).toHaveText(text(stage, "title"), { timeout: 30_000 });
      await expect(panel.locator("[data-field=what]")).toHaveText(text(stage, "what"));
      await expect(panel.locator("[data-field=why]")).toHaveText(text(stage, "why"));
    });
  }

  await test.step("prompt and camera card explainers", async () => {
    await expect(page.getByTestId("prompt")).toHaveText(text("prompt.light", "text"));
    const fps = page.getByRole("group", { name: text("field.fps", "title") });
    await fps.locator("summary").click();
    await expect(fps.locator("[data-field=text]")).toHaveText(text("field.fps", "text"));
    for (const key of ["field.channel", "field.browser", "field.camera_label", "field.resolution", "field.clock_source", "field.gyro"]) {
      await expect(page.getByRole("group", { name: text(key, "title") })).toBeVisible();
    }
  });

  await expect(page.getByRole("heading", { name: "Recording saved" })).toBeVisible({ timeout: 90_000 });

  await test.step("labelled bundle on disk", () => {
    const meta = JSON.parse(readFileSync(path.join(server.bundle, "meta.json"), "utf8"));
    expect(meta.mode).toBe("superset");
    expect(meta.product).toBe("lab");
    expect(meta.label).toEqual({
      person: "P07", device: "D02", light: "dim", kind: "genuine", tool: null, consent_ref: "C-2026-07",
    });
    expect(meta.camera_details.channel).toBe("desktop_browser");
    const frames = readFileSync(path.join(server.bundle, "frames.jsonl"), "utf8").trim().split("\n");
    expect(frames.length).toBeGreaterThanOrEqual(100);
    const pulses = readFileSync(path.join(server.bundle, "pulses.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
    expect(pulses).toHaveLength(10);
    expect(pulses.every((p) => p.ok)).toBe(true);
  });
});

test("Record fits a 360 px phone screen without sideways scrolling", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 360, height: 740 });
  const server = new MockServer(testInfo.outputPath("bundles"));
  await server.install(page);
  await page.goto("http://localhost:5173/record");
  const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
  await page.getByLabel("Attack", { exact: true }).check();
  await page.getByRole("button", { name: "Continue" }).click(); // shows every validation message
  expect(await fits()).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("record-form-360.png"), fullPage: true });
  await page.getByLabel("Person code").fill("P01");
  await page.getByLabel("Device code").fill("D01");
  await page.getByLabel("Attack tool").selectOption("liveswap");
  await page.getByLabel("Consent reference").fill("C-01");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("group", { name: "Measured frame rate" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("group", { name: "Measured frame rate" }).locator("summary").click();
  expect(await fits()).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("record-session-360.png"), fullPage: true });
});
