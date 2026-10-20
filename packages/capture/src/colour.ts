/**
 * Equal-luminance ("isoluminant") colours for the light suite (SPEC 7.4).
 *
 * Colours sit on a circle around a neutral grey in linear sRGB, inside the plane where relative luminance
 * stays constant. Pulses change the colour of the light on the face, not its brightness, so the screen
 * does not visibly flicker and the echo is a chromaticity shift the analysis can project on (SPEC 9.3).
 */

export type RGB = readonly [number, number, number];

/** Rec. 709 / sRGB relative-luminance weights for linear RGB. */
const W: RGB = [0.2126, 0.7152, 0.0722];

/**
 * Neutral luminance between pulses. 0.5 gives the widest isoluminant circle in linear sRGB (radius ~0.5,
 * limited by channels hitting 0 below and 1 above), so colour pulses are as strong as they can be.
 */
export const NEUTRAL_LUMINANCE = 0.5;

/** Share of the largest in-gamut radius used, leaving room for 8-bit rounding. */
const SATURATION = 0.95;

export const srgbToLinear = (c: number): number => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
export const linearToSrgb = (c: number): number => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

/** Relative luminance (0..1) of an 8-bit sRGB colour. */
export function relativeLuminance(rgb: RGB): number {
  return rgb.reduce((sum, c, k) => sum + W[k]! * srgbToLinear(c / 255), 0);
}

const dot = (a: RGB, b: RGB) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const scale = (a: RGB, s: number): RGB => [a[0] * s, a[1] * s, a[2] * s];
const sub = (a: RGB, b: RGB): RGB => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const unit = (a: RGB) => scale(a, 1 / Math.sqrt(dot(a, a)));
const cross = (a: RGB, b: RGB): RGB => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

// Orthonormal basis of the constant-luminance plane (W·x = 0). Hue 0 points towards red.
const RED: RGB = [1, 0, 0];
const U = unit(sub(RED, scale(W, dot(W, RED) / dot(W, W))));
const V = unit(cross(W, U));

function direction(hueDeg: number): RGB {
  const h = (hueDeg * Math.PI) / 180;
  return [Math.cos(h) * U[0] + Math.sin(h) * V[0], Math.cos(h) * U[1] + Math.sin(h) * V[1], Math.cos(h) * U[2] + Math.sin(h) * V[2]];
}

/** Largest radius at which every hue stays inside [0, 1] in linear RGB around grey Y. */
const radiusCache = new Map<number, number>();
function radius(Y: number): number {
  let r = radiusCache.get(Y);
  if (r === undefined) {
    r = Infinity;
    for (let h = 0; h < 360; h += 0.5) {
      for (const d of direction(h)) {
        if (d > 1e-12) r = Math.min(r, (1 - Y) / d);
        else if (d < -1e-12) r = Math.min(r, Y / -d);
      }
    }
    r *= SATURATION;
    radiusCache.set(Y, r);
  }
  return r;
}

const to8bit = (linear: RGB): RGB =>
  linear.map((c) => Math.round(255 * linearToSrgb(Math.min(1, Math.max(0, c))))) as unknown as RGB;

/** 8-bit sRGB colour of the given hue with relative luminance Y (to within 8-bit rounding). */
export function isoluminantColour(hueDeg: number, Y = NEUTRAL_LUMINANCE): RGB {
  const d = direction(hueDeg);
  const r = radius(Y);
  return to8bit([Y + r * d[0], Y + r * d[1], Y + r * d[2]]);
}

/** The light-suite colour set: n hues evenly spaced from 0 degrees. */
export function isoluminantColours(Y = NEUTRAL_LUMINANCE, n = 6): { hue: number; rgb: RGB }[] {
  return Array.from({ length: n }, (_, k) => {
    const hue = (360 * k) / n;
    return { hue, rgb: isoluminantColour(hue, Y) };
  });
}

/** Grey shown between pulses, at the same luminance as the colours. */
export function neutralColour(Y = NEUTRAL_LUMINANCE): RGB {
  return to8bit([Y, Y, Y]);
}

export const WHITE: RGB = [255, 255, 255];

export const cssColour = (rgb: RGB) => `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
