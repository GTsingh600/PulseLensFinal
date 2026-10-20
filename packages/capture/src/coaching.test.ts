import { describe, expect, it } from "vitest";
import { coachTips, laplacianVariance, meanLuma, type CoachMetrics } from "./coaching";

function image(w: number, h: number, f: (x: number, y: number) => number): Uint8ClampedArray {
  const d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const v = f(x, y);
      d.set([v, v, v, 255], (y * w + x) * 4);
    }
  }
  return d;
}

const good: CoachMetrics = { faceFrac: 0.12, meanLuma: 120, faceLuma: 130, backgroundLuma: 110, sharpness: 150 };

describe("coaching metrics", () => {
  it("measures mean luma inside a box", () => {
    const d = image(10, 10, (x) => (x < 5 ? 0 : 200));
    expect(meanLuma(d, 10, 10)).toBeCloseTo(100, 5);
    expect(meanLuma(d, 10, 10, { x: 5, y: 0, w: 5, h: 10 })).toBeCloseTo(200, 5);
  });

  it("finds a sharp checkerboard sharper than a flat field", () => {
    const sharp = laplacianVariance(image(32, 32, (x, y) => ((x + y) % 2 ? 255 : 0)), 32, 32);
    const flat = laplacianVariance(image(32, 32, () => 128), 32, 32);
    expect(flat).toBe(0);
    expect(sharp).toBeGreaterThan(1000);
  });
});

describe("coachTips (SPEC 7.5)", () => {
  it("always shows the brightness tip once, in the first round", () => {
    expect(coachTips(good, 1)).toEqual(["prompt.coach.brightness"]);
    expect(coachTips(good, 2)).toEqual([]);
  });

  it("asks to move closer when the face is small or missing", () => {
    expect(coachTips({ ...good, faceFrac: 0.01 }, 2)).toEqual(["prompt.coach.closer"]);
    expect(coachTips({ ...good, faceFrac: 0 }, 2)).toEqual(["prompt.coach.closer"]);
  });

  it("asks for light in a dark room", () => {
    expect(coachTips({ ...good, meanLuma: 25, faceLuma: 25, backgroundLuma: 25 }, 2)).toContain("prompt.coach.light");
  });

  it("detects a light behind the person", () => {
    expect(coachTips({ ...good, faceLuma: 50, backgroundLuma: 200 }, 2)).toContain("prompt.coach.backlight");
  });

  it("asks to hold still on a blurred picture", () => {
    expect(coachTips({ ...good, sharpness: 2 }, 2)).toContain("prompt.coach.steady");
  });

  it("skips face tips when no face detector is available (abstain, not a complaint)", () => {
    expect(coachTips({ ...good, faceFrac: null, faceLuma: null }, 2)).toEqual([]);
  });
});
