/**
 * Coaching (SPEC 7.5): measure the picture in the browser for 3 s, show tips, at most 2 rounds, then go on.
 * Low quality is never a fail here; later checks abstain on it instead.
 */
import { config } from "@pulselens/types";

export type CoachTipKey =
  | "prompt.coach.closer"
  | "prompt.coach.light"
  | "prompt.coach.backlight"
  | "prompt.coach.steady"
  | "prompt.coach.brightness";

export interface CoachMetrics {
  /** face box area / frame area; 0 = no face found; null = no face detector available */
  faceFrac: number | null;
  /** mean luma (0-255) of the whole frame */
  meanLuma: number;
  /** mean luma of the face box; null without a face */
  faceLuma: number | null;
  /** mean luma outside the face box (the whole frame without a face) */
  backgroundLuma: number;
  /** variance of the Laplacian (face box, else whole frame); low = blurred */
  sharpness: number;
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Tip thresholds. Starting points only, set to be lenient: tips help, they never score anyone.
 * Tune them from G1 sessions if tips fire on good pictures.
 */
export const COACH_LIMITS = {
  /** face smaller than this share of the frame → move closer (abstain level is quality.min_face_frac) */
  minFaceFrac: config.quality.min_face_frac * 2.5,
  /** frame darker than this → face a light */
  minLuma: config.quality.luma_range[0],
  /** face darker than this share of the background, on a bright background → light behind you */
  backlightRatio: 0.6,
  minBackgroundForBacklight: 100,
  /** Laplacian variance below this → hold still or wipe the camera */
  minSharpness: 15,
} as const;

const luma = (d: Uint8ClampedArray, k: number) => 0.299 * d[k]! + 0.587 * d[k + 1]! + 0.114 * d[k + 2]!;

function clip(box: Box | undefined, w: number, h: number): Box {
  if (!box) return { x: 0, y: 0, w, h };
  const x = Math.max(0, Math.floor(box.x));
  const y = Math.max(0, Math.floor(box.y));
  return { x, y, w: Math.max(0, Math.min(w, Math.ceil(box.x + box.w)) - x), h: Math.max(0, Math.min(h, Math.ceil(box.y + box.h)) - y) };
}

/** Mean luma (0-255) of RGBA pixels, optionally inside a box. */
export function meanLuma(d: Uint8ClampedArray, w: number, h: number, box?: Box): number {
  const b = clip(box, w, h);
  let sum = 0;
  for (let y = b.y; y < b.y + b.h; y++) for (let x = b.x; x < b.x + b.w; x++) sum += luma(d, (y * w + x) * 4);
  return b.w * b.h ? sum / (b.w * b.h) : 0;
}

/** Mean luma outside a box. */
export function meanLumaOutside(d: Uint8ClampedArray, w: number, h: number, box: Box): number {
  const b = clip(box, w, h);
  const total = meanLuma(d, w, h) * w * h;
  const inside = meanLuma(d, w, h, b) * b.w * b.h;
  const n = w * h - b.w * b.h;
  return n > 0 ? (total - inside) / n : 0;
}

/** Variance of the 4-neighbour Laplacian of luma: the usual quick blur measure. */
export function laplacianVariance(d: Uint8ClampedArray, w: number, h: number, box?: Box): number {
  const b = clip(box, w, h);
  let n = 0;
  let sum = 0;
  let sum2 = 0;
  for (let y = Math.max(1, b.y); y < Math.min(h - 1, b.y + b.h); y++) {
    for (let x = Math.max(1, b.x); x < Math.min(w - 1, b.x + b.w); x++) {
      const k = (y * w + x) * 4;
      const lap = luma(d, k - 4) + luma(d, k + 4) + luma(d, k - 4 * w) + luma(d, k + 4 * w) - 4 * luma(d, k);
      sum += lap;
      sum2 += lap * lap;
      n++;
    }
  }
  if (!n) return 0;
  const mean = sum / n;
  return Math.max(0, sum2 / n - mean * mean);
}

/** Tips for one round. The brightness tip is always shown once (browsers can't set brightness). */
export function coachTips(m: CoachMetrics, round: number): CoachTipKey[] {
  const tips: CoachTipKey[] = [];
  if (m.faceFrac !== null && m.faceFrac < COACH_LIMITS.minFaceFrac) tips.push("prompt.coach.closer");
  if (m.meanLuma < COACH_LIMITS.minLuma) tips.push("prompt.coach.light");
  else if (
    m.faceLuma !== null &&
    m.backgroundLuma >= COACH_LIMITS.minBackgroundForBacklight &&
    m.faceLuma < COACH_LIMITS.backlightRatio * m.backgroundLuma
  ) {
    tips.push("prompt.coach.backlight");
  }
  if (m.sharpness < COACH_LIMITS.minSharpness) tips.push("prompt.coach.steady");
  if (round === 1) tips.push("prompt.coach.brightness");
  return tips;
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)]! : 0;
};

/** Face box finder: MediaPipe FaceDetector in the app, null when the model can't load. */
export type FaceFinder = (video: HTMLVideoElement, t: number) => Box | null;

/** Loads the MediaPipe BlazeFace detector from the dev server (`/mediapipe/wasm`, `/models/...`). */
export async function loadFaceFinder(
  wasmBase = "/mediapipe/wasm",
  model = "/models/mediapipe/blaze_face_short_range.tflite",
): Promise<FaceFinder | null> {
  try {
    const { FaceDetector, FilesetResolver } = await import("@mediapipe/tasks-vision");
    const fileset = await FilesetResolver.forVisionTasks(wasmBase);
    const detector = await FaceDetector.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: model, delegate: "CPU" },
      runningMode: "VIDEO",
    });
    let last = -1;
    return (video, t) => {
      const ts = Math.max(t, last + 1); // MediaPipe needs strictly increasing timestamps
      last = ts;
      const best = detector.detectForVideo(video, ts).detections[0]?.boundingBox;
      return best ? { x: best.originX, y: best.originY, w: best.width, h: best.height } : null;
    };
  } catch (e) {
    console.warn("Face detector unavailable; coaching skips face tips.", e);
    return null;
  }
}

export interface CoachRound {
  round: number;
  metrics: CoachMetrics;
  tips: CoachTipKey[];
}

export interface CoachOptions {
  findFace: FaceFinder | null;
  now: () => number;
  measureMs?: number;
  /** how long tips stay up before the next round measures again */
  tipMs?: number;
  rounds?: number;
  onTips?: (round: CoachRound) => void;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Measures one round: samples about 5 frames per second at 160 px wide. */
export async function measure(video: HTMLVideoElement, opts: CoachOptions): Promise<CoachMetrics> {
  const w = 160;
  const h = Math.max(1, Math.round((w * video.videoHeight) / Math.max(1, video.videoWidth)));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  const samples: CoachMetrics[] = [];
  const end = opts.now() + (opts.measureMs ?? 3000);
  while (opts.now() < end) {
    ctx.drawImage(video, 0, 0, w, h);
    const d = ctx.getImageData(0, 0, w, h).data;
    const raw = opts.findFace ? opts.findFace(video, opts.now()) : undefined;
    const sx = w / Math.max(1, video.videoWidth);
    const face = raw ? { x: raw.x * sx, y: raw.y * sx, w: raw.w * sx, h: raw.h * sx } : null;
    samples.push({
      faceFrac: raw === undefined ? null : face ? (face.w * face.h) / (w * h) : 0,
      meanLuma: meanLuma(d, w, h),
      faceLuma: face ? meanLuma(d, w, h, face) : null,
      backgroundLuma: face ? meanLumaOutside(d, w, h, face) : meanLuma(d, w, h),
      sharpness: laplacianVariance(d, w, h, face ?? undefined),
    });
    await sleep(200);
  }
  const faces = samples.filter((s) => s.faceLuma !== null);
  const faceFracs = samples.map((s) => s.faceFrac).filter((f): f is number => f !== null);
  return {
    faceFrac: faceFracs.length ? median(faceFracs) : null,
    meanLuma: median(samples.map((s) => s.meanLuma)),
    faceLuma: faces.length ? median(faces.map((s) => s.faceLuma!)) : null,
    backgroundLuma: median(samples.map((s) => s.backgroundLuma)),
    sharpness: median(samples.map((s) => s.sharpness)),
  };
}

/** Runs up to `rounds` rounds; a second round only when the first found something to fix. */
export async function runCoaching(video: HTMLVideoElement, opts: CoachOptions): Promise<CoachRound[]> {
  const rounds: CoachRound[] = [];
  for (let round = 1; round <= (opts.rounds ?? 2); round++) {
    const metrics = await measure(video, opts);
    const result = { round, metrics, tips: coachTips(metrics, round) };
    rounds.push(result);
    opts.onTips?.(result);
    if (result.tips.every((t) => t === "prompt.coach.brightness")) break;
    await sleep(opts.tipMs ?? 3000);
  }
  return rounds;
}
