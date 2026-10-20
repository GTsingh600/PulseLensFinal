// @vitest-environment jsdom
import type { PulseMessage } from "@pulselens/types";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isoluminantColour, neutralColour } from "./colour";
import { LightOverlay, LightPulseExecutor, type Fill } from "./light";

function pulse(params: Record<string, unknown>, id = "p1"): PulseMessage {
  return { type: "pulse", pulse_id: id, kind: "light", source: "orchestrator", params, sig: "abc" };
}

describe("LightPulseExecutor (SPEC 7.4 timing)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "requestAnimationFrame", "performance"] });
  });
  afterEach(() => vi.useRealTimers());

  it("paints, records received <= applied < painted < ended, then returns to neutral", async () => {
    const overlay = new LightOverlay({ mode: "fullscreen" });
    overlay.mount(document.body);
    const exec = new LightPulseExecutor(overlay);
    const run = exec.run(pulse({ mode: "colour", hue_deg: 120, duration_ms: 400 }), performance.now());
    await vi.advanceTimersByTimeAsync(1000);
    const ack = await run;
    expect(ack).toMatchObject({ type: "ack", pulse_id: "p1", sig: "abc", ok: true, error: null });
    expect(ack.applied!).toBeGreaterThanOrEqual(ack.received);
    expect(ack.painted!).toBeGreaterThan(ack.applied!);
    expect(ack.ended! - ack.painted!).toBeGreaterThanOrEqual(400);
    expect(ack.shown).toEqual({ neutral: [...neutralColour()], rgb: [...isoluminantColour(120)] });
    expect(overlay.current).toEqual({ left: neutralColour(), right: neutralColour() });
    overlay.unmount();
  });

  it("paints split pulses as two halves", async () => {
    const overlay = new LightOverlay({ mode: "border" });
    overlay.mount(document.body);
    const exec = new LightPulseExecutor(overlay);
    const seen: Fill[] = [];
    overlay.onPaint = (fill) => seen.push(fill);
    const run = exec.run(pulse({ mode: "split", left_hue_deg: 0, right_hue_deg: 180, duration_ms: 400 }), performance.now());
    await vi.advanceTimersByTimeAsync(1000);
    expect((await run).shown).toMatchObject({ left: [...isoluminantColour(0)], right: [...isoluminantColour(180)] });
    expect(seen[0]).toEqual({ left: isoluminantColour(0), right: isoluminantColour(180) });
    overlay.unmount();
  });

  it("rejects bad params, and a 4th flash inside one second, without painting", async () => {
    const overlay = new LightOverlay({ mode: "fullscreen" });
    overlay.mount(document.body);
    const exec = new LightPulseExecutor(overlay);
    const bad = await exec.run(pulse({ mode: "rainbow", duration_ms: 400 }), performance.now());
    expect(bad).toMatchObject({ ok: false, error: "bad_params", painted: null });

    const acks = [];
    for (let k = 0; k < 4; k++) {
      const run = exec.run(pulse({ mode: "white", duration_ms: 50 }, `w${k}`), performance.now());
      await vi.advanceTimersByTimeAsync(120);
      acks.push(await run);
    }
    expect(acks.map((a) => a.ok)).toEqual([true, true, true, false]);
    expect(acks[3]!.error).toBe("rate_limit");
    overlay.unmount();
  });
});
