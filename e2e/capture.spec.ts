// M1.4 acceptance (Chromium fake camera): details posted, ≥ 200 frames with increasing t,
// a fingerprint frame every 5th frame, 10 pulse acks in order.
import { expect, test } from "@playwright/test";
import { config } from "../packages/types/src/config.gen";
import { MockServer } from "./support/mock-server";

test("capture core records a full light suite", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const server = new MockServer(testInfo.outputPath("bundles"));
  await server.install(page);
  await page.goto("http://localhost:5173/capture-harness.html");
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.locator("body")).toHaveAttribute("data-phase", "done", { timeout: 110_000 });

  await test.step("details posted", () => {
    expect(server.detailPosts.length).toBeGreaterThanOrEqual(2); // full details, then fps updates
    const d = server.details;
    expect(d.channel).toBe("desktop_browser");
    expect(["captureTime", "rvfc", "videoframe", "raf"]).toContain(d.clock_source);
    expect(d.settings?.width).toBeGreaterThan(0);
    expect(d.fps_median).toBeGreaterThan(5);
    expect(d.webdriver).toBe(true); // Playwright sets navigator.webdriver, and the details report it
    expect(d.device_id_hash).toMatch(/^[0-9a-f]{16}$/);
    expect(d.gyro).toBe("absent"); // a laptop has no motion sensor; never "denied" without a prompt
    expect(server.roles).toEqual(["lab"]);
  });

  await test.step("≥ 200 frames with strictly increasing t", () => {
    const frames = [...server.frames].sort((a, b) => a.i - b.i);
    expect(frames.length).toBeGreaterThanOrEqual(200);
    for (let k = 1; k < frames.length; k++) expect(frames[k]!.t).toBeGreaterThan(frames[k - 1]!.t);
    expect(new Set(server.workingFiles).size).toBe(frames.length);
  });

  await test.step("a fingerprint frame every 5th frame", () => {
    const every = config.capture.fp_every;
    for (const f of server.frames) expect(f.fp_file !== null, `frame ${f.i}`).toBe(f.i % every === 0);
    expect(server.fpFiles.sort()).toEqual(server.frames.filter((f) => f.fp_file).map((f) => f.fp_file).sort());
  });

  await test.step("10 pulse acks in order", () => {
    expect(server.released).toHaveLength(10);
    expect(server.acks.map((a) => a.pulse_id)).toEqual(server.released.map((p) => p.pulse_id));
    for (const a of server.acks) {
      expect(a.ok, a.error ?? "").toBe(true);
      expect(a.sig).toBe(server.released.find((p) => p.pulse_id === a.pulse_id)!.sig);
      expect(a.applied!).toBeGreaterThanOrEqual(a.received);
      expect(a.painted!).toBeGreaterThan(a.applied!);
      expect(a.ended! - a.painted!).toBeGreaterThanOrEqual(config.pulses.light.duration_ms - 20);
    }
    for (let k = 1; k < server.acks.length; k++) expect(server.acks[k]!.received).toBeGreaterThan(server.acks[k - 1]!.ended!);
  });

  await test.step("bundle finalized", () => {
    expect(server.finalized).toMatchObject({ dropped: 0, acks_ok: 10 });
    expect(server.stagesDone.map((s) => s.stage)).toEqual(["camera", "coach"]);
  });
});
