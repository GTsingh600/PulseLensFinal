// @vitest-environment jsdom
import { config } from "@pulselens/types";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fitSize, frameFile, FrameGrabber, type GrabbedFrame } from "./grabber";

type Md = { captureTime?: number; presentedFrames: number };
type Cb = (now: number, md: Md) => void;

/** A video element whose requestVideoFrameCallback the test fires by hand. */
function fakeVideo(w = 640, h = 480) {
  let pending: Cb | null = null;
  const video = document.createElement("video");
  Object.defineProperty(video, "videoWidth", { value: w });
  Object.defineProperty(video, "videoHeight", { value: h });
  (video as unknown as { requestVideoFrameCallback: (cb: Cb) => number }).requestVideoFrameCallback = (cb) => {
    pending = cb;
    return 1;
  };
  const fire = (now: number, md: Md) => {
    const cb = pending!;
    pending = null;
    cb(now, md);
  };
  return { video, fire };
}

const encoder = {
  encode: vi.fn(async (_src: CanvasImageSource, _w: number, _h: number, _q: number) => new Blob()),
  close: vi.fn(),
};

function grabber(video: HTMLVideoElement, mobile = false) {
  const frames: GrabbedFrame[] = [];
  const g = new FrameGrabber(video, { mobile, onFrame: (f) => frames.push(f), source: "rvfc", encoder });
  return { g, frames };
}

const proto = HTMLVideoElement.prototype as unknown as Record<string, unknown>;
proto.requestVideoFrameCallback ??= () => 0;

afterEach(() => encoder.encode.mockClear());

describe("fitSize and frameFile", () => {
  it("fits inside the box in the frame's own orientation and never upscales", () => {
    expect(fitSize(1280, 720, [640, 480])).toEqual([640, 360]);
    expect(fitSize(720, 1280, [640, 480])).toEqual([360, 640]); // portrait phone: the box turns to 480x640
    expect(fitSize(320, 240, [640, 480])).toEqual([320, 240]);
    expect(fitSize(0, 0, [640, 480])).toEqual([1, 1]);
  });

  it("names frames with six digits, as the server's FRAME_NAME expects", () => {
    expect(frameFile(7)).toBe("000007.jpg");
    expect(frameFile(123456)).toBe("123456.jpg");
  });
});

describe("FrameGrabber (rVFC)", () => {
  it("uses captureTime as t and labels the clock source", () => {
    const { video, fire } = fakeVideo();
    const { g, frames } = grabber(video);
    g.start();
    fire(1100, { captureTime: 1000, presentedFrames: 1 });
    fire(1133, { captureTime: 1033, presentedFrames: 2 });
    expect(g.clockSource).toBe("captureTime");
    expect(frames.map((f) => f.meta.t)).toEqual([1000, 1033]);
    expect(frames.map((f) => f.meta.capture_time)).toEqual([1000, 1033]);
  });

  it("keeps one clock when a frame arrives without captureTime: shifts by the last latency", () => {
    const { video, fire } = fakeVideo();
    const { g, frames } = grabber(video);
    g.start();
    fire(1100, { captureTime: 1000, presentedFrames: 1 });
    fire(1140, { presentedFrames: 2 }); // no captureTime: 1140 - 100 latency
    expect(frames[1]!.meta.t).toBe(1040);
    expect(frames[1]!.meta.capture_time).toBeNull();
  });

  it("falls back to the callback time when the browser never gives captureTime", () => {
    const { video, fire } = fakeVideo();
    const { g, frames } = grabber(video);
    g.start();
    fire(500, { presentedFrames: 1 });
    expect(g.clockSource).toBe("rvfc");
    expect(frames[0]!.meta.t).toBe(500);
  });

  it("skips frames whose time does not move forward, so t strictly increases", () => {
    const { video, fire } = fakeVideo();
    const { g, frames } = grabber(video);
    g.start();
    for (const [now, ct] of [[100, 50], [140, 50], [150, 40], [180, 83]] as const) fire(now, { captureTime: ct, presentedFrames: 0 });
    expect(frames.map((f) => f.meta.t)).toEqual([50, 83]);
    expect(frames.map((f) => f.meta.i)).toEqual([0, 1]);
  });

  it("adds a native-size fingerprint frame every fp_every frames, capped at fp_max", () => {
    const { video, fire } = fakeVideo(1920, 1080);
    const { g, frames } = grabber(video);
    g.start();
    for (let k = 0; k < 11; k++) fire(1000 + 33 * k, { captureTime: 1000 + 33 * k, presentedFrames: k });
    const withFp = frames.filter((f) => f.fp).map((f) => f.meta.i);
    expect(withFp).toEqual([0, config.capture.fp_every, 2 * config.capture.fp_every].filter((i) => i < 11));
    const fpCall = encoder.encode.mock.calls.find((c) => c[3] === config.capture.fp_jpeg)!;
    expect([fpCall[1], fpCall[2]]).toEqual(fitSize(1920, 1080, config.capture.fp_max));
  });

  it("reports median fps and jitter once it has 5 intervals, like the 15.6 fps G1 laptop", () => {
    const { video, fire } = fakeVideo();
    const { g } = grabber(video);
    g.start();
    expect(g.stats().fpsMedian).toBeNull();
    const steps = [64, 64, 48, 64, 64, 48, 64];
    let t = 0;
    fire(t, { captureTime: t, presentedFrames: 0 });
    for (const d of steps) fire((t += d), { captureTime: t, presentedFrames: 0 });
    const s = g.stats();
    expect(s.fpsMedian).toBeCloseTo(1000 / 64, 3);
    expect(s.jitterMs).toBeGreaterThan(5);
    expect(s.frames).toBe(steps.length + 1);
  });

  it("stops asking for frames after stop()", () => {
    const { video, fire } = fakeVideo();
    const { g, frames } = grabber(video);
    g.start();
    fire(10, { captureTime: 10, presentedFrames: 1 });
    g.stop();
    fire(43, { captureTime: 43, presentedFrames: 2 });
    expect(frames).toHaveLength(1);
  });

  it("does not emit frames before the video has a size", () => {
    const { video, fire } = fakeVideo(0, 0);
    const { g, frames } = grabber(video);
    g.start();
    fire(10, { captureTime: 10, presentedFrames: 1 });
    expect(frames).toHaveLength(0);
  });
});
