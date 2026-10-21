/**
 * Stage-1 mode-switch probe (SPEC 7.3), about 3 to 5 s on a fresh track.
 *
 * Up to three requests with exact sizes and resizeMode "none": a common native mode, a second aspect ratio and an
 * unusual mode real webcams rarely offer. For each: apply_start/apply_end, ok or the error name (an
 * OverconstrainedError is data, not a failure), settings before and after, the first frame time whose size matches,
 * frames dropped during the switch, fps over the next second, and the times of a frame just before and one 500 ms
 * after (the server compares those two frames for the field-of-view change). Then the working mode is restored.
 * Without resizeMode (Safari, Firefox) the unusual mode is skipped and marked so.
 */
import { config } from "@pulselens/types";

export interface ProbeRow {
  step: number;
  request: { width: number; height: number; frameRate: number };
  unusual: boolean;
  skipped: boolean;
  reason: string | null;
  ok: boolean;
  error: string | null;
  apply_start: number | null;
  apply_end: number | null;
  settings_before: Record<string, unknown>;
  settings_after: Record<string, unknown>;
  first_match_t: number | null;
  missing_frames: number | null;
  fps_after: number | null;
  before_t: number | null;
  after_t: number | null;
}

export interface ProbeDeps {
  track: MediaStreamTrack;
  /** current decoded size of the video element */
  videoSize: () => [number, number];
  /** frame time of the next grabbed frame (performance.now() domain), or null after `timeoutMs` */
  nextFrame: (timeoutMs: number) => Promise<number | null>;
  /** frames grabbed so far */
  framesSeen: () => number;
  /** frames the browser dropped so far, when it reports them */
  dropped: () => number | null;
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  resizeModeSupported: boolean;
  modes?: readonly (readonly [number, number, number])[];
  settleMs?: number;
}

/** The working-mode request of SPEC 7.1, restored after the probe. */
export const WORKING_CONSTRAINTS: MediaTrackConstraints = {
  facingMode: "user",
  width: { ideal: 640 },
  height: { ideal: 480 },
  frameRate: { ideal: 30 },
};

const settingsOf = (track: MediaStreamTrack): Record<string, unknown> => {
  const s = { ...(track.getSettings?.() ?? {}) } as Record<string, unknown>;
  delete s.deviceId;
  delete s.groupId;
  return s;
};

export async function runProbe(deps: ProbeDeps): Promise<ProbeRow[]> {
  const modes = deps.modes ?? (config.probe.modes as unknown as [number, number, number][]);
  const settleMs = deps.settleMs ?? config.probe.settle_ms;
  const rows: ProbeRow[] = [];
  for (const [k, [width, height, frameRate]] of modes.entries()) {
    const unusual = k === 2;
    const row: ProbeRow = {
      step: k, request: { width, height, frameRate }, unusual, skipped: false, reason: null, ok: false, error: null,
      apply_start: null, apply_end: null, settings_before: settingsOf(deps.track), settings_after: {},
      first_match_t: null, missing_frames: null, fps_after: null, before_t: null, after_t: null,
    };
    if (unusual && !deps.resizeModeSupported) {
      rows.push({ ...row, skipped: true, reason: "resizeMode unsupported: the browser would rescale any mode" });
      continue;
    }
    row.before_t = await deps.nextFrame(settleMs);
    const droppedBefore = deps.dropped();
    row.apply_start = deps.now();
    try {
      await deps.track.applyConstraints({
        width: { exact: width }, height: { exact: height }, frameRate: { ideal: frameRate }, resizeMode: "none",
      } as MediaTrackConstraints);
      row.ok = true;
    } catch (e) {
      row.error = e instanceof Error ? e.name || e.message : String(e);
    }
    row.apply_end = deps.now();
    row.settings_after = settingsOf(deps.track);
    if (row.ok) {
      const deadline = row.apply_end + settleMs;
      while (deps.now() < deadline) {
        const t = await deps.nextFrame(deadline - deps.now());
        if (t === null) break;
        const [w, h] = deps.videoSize();
        if (w === width && h === height) {
          row.first_match_t = t;
          break;
        }
      }
      const droppedAfter = deps.dropped();
      row.missing_frames = droppedBefore !== null && droppedAfter !== null ? droppedAfter - droppedBefore : null;
      await deps.sleep(Math.max(0, row.apply_end + 500 - deps.now()));
      row.after_t = await deps.nextFrame(settleMs);
      const seen = deps.framesSeen();
      const start = deps.now();
      await deps.sleep(1000);
      row.fps_after = ((deps.framesSeen() - seen) * 1000) / Math.max(1, deps.now() - start);
    }
    rows.push(row);
  }
  await deps.track.applyConstraints(WORKING_CONSTRAINTS).catch(() => undefined);
  return rows;
}

/** The modes the camera really switched to (accepted and seen in the frames), for CameraDetails.native_modes. */
export function nativeModes(rows: ProbeRow[]): { width: number; height: number; frameRate: number }[] {
  return rows.filter((r) => r.ok && r.first_match_t !== null).map((r) => r.request);
}
