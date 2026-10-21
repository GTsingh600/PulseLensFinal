import { describe, expect, it, vi } from "vitest";
import { nativeModes, runProbe, WORKING_CONSTRAINTS, type ProbeDeps } from "./probe";

/**
 * A camera simulated in virtual time: each frame takes 33 ms; a switch to a supported mode takes `switchMs`
 * (the sensor reconfigures, during which `dropOnSwitch` frames are lost); unsupported modes throw.
 */
function camera(opts: { supported: [number, number][]; switchMs?: number; dropOnSwitch?: number; phantom?: boolean; resizeMode?: boolean }) {
  let clock = 0;
  let size: [number, number] = [640, 480];
  let pendingSize: [number, number] | null = null;
  let switchAt = 0;
  let frames = 0;
  let dropped = 0;
  let reported: [number, number] = [640, 480];
  const applied: MediaTrackConstraints[] = [];
  const track = {
    getSettings: () => ({ width: reported[0], height: reported[1], deviceId: "secret" }),
    applyConstraints: vi.fn(async (c: MediaTrackConstraints) => {
      applied.push(c);
      const w = (c.width as ConstrainULongRange | undefined)?.exact;
      const h = (c.height as ConstrainULongRange | undefined)?.exact;
      if (w === undefined || h === undefined) return; // the restore request
      if (!opts.supported.some(([a, b]) => a === w && b === h)) {
        throw Object.assign(new Error("Cannot satisfy constraints"), { name: "OverconstrainedError" });
      }
      clock += 5;
      reported = [w, h];
      if (!opts.phantom) {
        pendingSize = [w, h];
        switchAt = clock + (opts.switchMs ?? 200);
        dropped += opts.dropOnSwitch ?? 0;
      }
    }),
  } as unknown as MediaStreamTrack;
  const deps: ProbeDeps = {
    track,
    videoSize: () => size,
    nextFrame: async (timeoutMs) => {
      if (timeoutMs <= 0) return null;
      clock += 33;
      if (pendingSize && clock >= switchAt) {
        size = pendingSize;
        pendingSize = null;
      }
      frames += 1;
      return clock;
    },
    framesSeen: () => frames,
    dropped: () => dropped,
    now: () => clock,
    sleep: async (ms) => {
      frames += Math.floor(ms / 33);
      clock += ms;
    },
    resizeModeSupported: opts.resizeMode ?? true,
    settleMs: 1000,
  };
  return { deps, applied };
}

const REAL = [[1280, 720], [640, 480]] as [number, number][];

describe("runProbe (SPEC 7.3)", () => {
  it("logs a real webcam: two modes switch after a delay with dropped frames, the unusual one is refused", async () => {
    const { deps, applied } = camera({ supported: REAL, switchMs: 250, dropOnSwitch: 4 });
    const rows = await runProbe(deps);
    expect(rows.map((r) => [r.ok, r.error])).toEqual([[true, null], [true, null], [false, "OverconstrainedError"]]);
    const [hd] = rows;
    expect(hd!.first_match_t! - hd!.apply_start!).toBeGreaterThanOrEqual(250);
    expect(hd!.missing_frames).toBe(4);
    expect(hd!.settings_after).toMatchObject({ width: 1280, height: 720 });
    expect(hd!.settings_before).not.toHaveProperty("deviceId");
    expect(hd!.after_t! - hd!.apply_end!).toBeGreaterThanOrEqual(500);
    expect(hd!.fps_after).toBeGreaterThan(25);
    expect(rows[2]!.unusual).toBe(true);
    expect(applied.at(-1)).toEqual(WORKING_CONSTRAINTS); // restored
    expect(nativeModes(rows)).toEqual([{ width: 1280, height: 720, frameRate: 30 }, { width: 640, height: 480, frameRate: 30 }]);
  });

  it("records a phantom switch: settings change but frames never do", async () => {
    const { deps } = camera({ supported: REAL, phantom: true });
    const rows = await runProbe(deps);
    expect(rows[0]).toMatchObject({ ok: true, first_match_t: null, settings_after: { width: 1280, height: 720 } });
    expect(nativeModes(rows)).toEqual([{ width: 640, height: 480, frameRate: 30 }]); // only the mode it was already in
  });

  it("skips the unusual mode without resizeMode and says why", async () => {
    const { deps, applied } = camera({ supported: REAL, resizeMode: false });
    const rows = await runProbe(deps);
    expect(rows[2]).toMatchObject({ skipped: true, ok: false, apply_start: null });
    expect(rows[2]!.reason).toMatch(/resizeMode/);
    expect(applied).toHaveLength(3); // two requests and the restore, none for the skipped mode
  });

  it("accepts anything when software rescales (a virtual camera), which the server compares with genuine", async () => {
    const { deps } = camera({ supported: [...REAL, [1000, 750]], switchMs: 0, dropOnSwitch: 0 });
    const rows = await runProbe(deps);
    expect(rows.every((r) => r.ok)).toBe(true);
    expect(rows.map((r) => r.missing_frames)).toEqual([0, 0, 0]);
  });
});
