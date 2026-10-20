import { config } from "@pulselens/types";
import { describe, expect, it } from "vitest";
import { FlashLimiter } from "./flash";

describe("FlashLimiter (M1.4 acceptance: at most 3 flashes per second)", () => {
  it("refuses a 4th flash inside any 1 s window", () => {
    const l = new FlashLimiter();
    for (const t of [0, 200, 400]) {
      expect(l.allow(t)).toBe(true);
      l.record(t);
    }
    expect(l.allow(600)).toBe(false);
    expect(l.allow(999)).toBe(false);
    expect(l.allow(1001)).toBe(true);
  });

  it("never lets any 1 s window hold more than 3 onsets, whatever the request times", () => {
    const l = new FlashLimiter();
    const onsets: number[] = [];
    for (let t = 0; t < 10_000; t += 37 + ((t * 7919) % 113)) {
      if (l.allow(t)) {
        l.record(t);
        onsets.push(t);
      }
    }
    for (const s of onsets) expect(onsets.filter((t) => t >= s && t < s + 1000).length).toBeLessThanOrEqual(3);
  });

  it("is always satisfied by the configured light-suite spacing", () => {
    const { duration_ms, gap_ms } = config.pulses.light;
    expect(1000 / (duration_ms + gap_ms[0])).toBeLessThanOrEqual(3);
  });
});
