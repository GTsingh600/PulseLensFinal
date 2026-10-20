import { describe, expect, it } from "vitest";
import {
  NEUTRAL_LUMINANCE,
  isoluminantColour,
  isoluminantColours,
  linearToSrgb,
  neutralColour,
  relativeLuminance,
  srgbToLinear,
} from "./colour";

describe("sRGB transfer", () => {
  it("round-trips linear and encoded values", () => {
    for (const v of [0, 0.001, 0.04, 0.2, 0.5, 0.9, 1]) expect(srgbToLinear(linearToSrgb(v))).toBeCloseTo(v, 6);
  });

  it("gives luminance 1 for white and 0 for black", () => {
    expect(relativeLuminance([255, 255, 255])).toBeCloseTo(1, 6);
    expect(relativeLuminance([0, 0, 0])).toBe(0);
  });
});

describe("isoluminantColours (M1.4 acceptance: within ±5% luminance)", () => {
  for (const Y of [0.3, NEUTRAL_LUMINANCE, 0.6]) {
    it(`keeps all six colours and the neutral within ±5% of each other at Y=${Y}`, () => {
      const lums = [...isoluminantColours(Y).map((c) => relativeLuminance(c.rgb)), relativeLuminance(neutralColour(Y))];
      const max = Math.max(...lums);
      const min = Math.min(...lums);
      expect((max - min) / min).toBeLessThanOrEqual(0.05);
      for (const l of lums) expect(Math.abs(l - Y) / Y).toBeLessThanOrEqual(0.05);
    });
  }

  it("holds for any hue, as split pulses use arbitrary pairs", () => {
    for (let h = 0; h < 360; h += 7) {
      const l = relativeLuminance(isoluminantColour(h));
      expect(Math.abs(l - NEUTRAL_LUMINANCE) / NEUTRAL_LUMINANCE).toBeLessThanOrEqual(0.05);
    }
  });

  it("returns six distinct, clearly coloured hues 60 degrees apart", () => {
    const set = isoluminantColours();
    expect(set.map((c) => c.hue)).toEqual([0, 60, 120, 180, 240, 300]);
    for (const c of set) {
      for (const ch of c.rgb) expect(Number.isInteger(ch) && ch >= 0 && ch <= 255).toBe(true);
      expect(Math.max(...c.rgb) - Math.min(...c.rgb)).toBeGreaterThan(60); // visibly coloured, not grey
    }
    expect(new Set(set.map((c) => c.rgb.join(","))).size).toBe(6);
  });
});
