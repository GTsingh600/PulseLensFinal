/**
 * Frame grabber (SPEC 7.2). One clock: every frame time `t` is in the performance.now() domain.
 *
 * - rvfc (preferred): video.requestVideoFrameCallback; t = metadata.captureTime ?? callback time.
 * - videoframe (opt-in, Chrome): MediaStreamTrackProcessor; VideoFrame.timestamp mapped once to performance.now().
 * - raf (fallback): requestAnimationFrame, a new frame when the decoded-frame count changes.
 *
 * Every frame gets a working JPEG at the working size; every fp_every-th frame also gets a fingerprint JPEG at
 * native size (capped at fp_max). Frames with a time not after the previous one are skipped, so t strictly increases.
 */
import { config, type ClockSource, type FrameMeta } from "@pulselens/types";
import { now } from "./clock";
import { createEncoder, type FrameEncoder } from "./encoder";

export interface GrabbedFrame {
  meta: FrameMeta;
  working: Promise<Blob>;
  fp?: Promise<Blob>;
}

export type GrabberSource = "auto" | "rvfc" | "videoframe" | "raf";

export interface GrabberOptions {
  mobile: boolean;
  onFrame: (frame: GrabbedFrame) => void;
  source?: GrabberSource;
  encoder?: FrameEncoder;
}

export interface GrabberStats {
  frames: number;
  fpsMedian: number | null;
  jitterMs: number | null;
}

interface VideoFrameLike {
  timestamp: number; // microseconds
  close(): void;
}
type ProcessorCtor = new (init: { track: MediaStreamTrack }) => { readable: ReadableStream<VideoFrameLike> };

/** Fits (w, h) inside a box of the same orientation, never upscaling. */
export function fitSize(w: number, h: number, box: readonly [number, number]): [number, number] {
  const [bw, bh] = w >= h ? box : [box[1], box[0]];
  const s = Math.min(1, bw / w, bh / h);
  return [Math.max(1, Math.round(w * s)), Math.max(1, Math.round(h * s))];
}

export const frameFile = (i: number) => `${String(i).padStart(6, "0")}.jpg`;

export class FrameGrabber {
  clockSource: ClockSource | null = null;
  private running = false;
  private i = 0;
  private lastT = -Infinity;
  private captureOffset: number | null = null;
  private intervals: number[] = [];
  private readonly encoder: FrameEncoder;
  private stopVideoFrame?: () => void;

  constructor(
    private readonly video: HTMLVideoElement,
    private readonly opts: GrabberOptions,
  ) {
    this.encoder = opts.encoder ?? createEncoder();
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    const source = this.opts.source ?? "auto";
    const hasRvfc = "requestVideoFrameCallback" in HTMLVideoElement.prototype;
    const Processor = (globalThis as unknown as { MediaStreamTrackProcessor?: ProcessorCtor }).MediaStreamTrackProcessor;
    if (source === "videoframe" && Processor) this.runVideoFrame(Processor);
    else if ((source === "auto" || source === "rvfc") && hasRvfc) this.runRvfc();
    else this.runRaf();
  }

  stop(): void {
    this.running = false;
    this.stopVideoFrame?.();
  }

  close(): void {
    this.stop();
    this.encoder.close();
  }

  stats(): GrabberStats {
    const xs = [...this.intervals].sort((a, b) => a - b);
    if (xs.length < 5) return { frames: this.i, fpsMedian: null, jitterMs: null };
    const median = xs[Math.floor(xs.length / 2)]!;
    const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
    const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / xs.length);
    return { frames: this.i, fpsMedian: 1000 / median, jitterMs: sd };
  }

  private runRvfc(): void {
    const loop = (cbNow: number, md: VideoFrameCallbackMetadata) => {
      if (!this.running) return;
      const capture = md.captureTime;
      this.clockSource ??= capture !== undefined ? "captureTime" : "rvfc";
      let t = cbNow;
      if (this.clockSource === "captureTime") {
        // Keep one domain: if a frame lacks captureTime, shift the callback time by the last known latency.
        if (capture !== undefined) this.captureOffset = cbNow - capture;
        t = capture ?? cbNow - (this.captureOffset ?? 0);
      }
      this.grab(this.video, t, capture ?? null, md.presentedFrames);
      this.video.requestVideoFrameCallback(loop);
    };
    this.video.requestVideoFrameCallback(loop);
  }

  private runRaf(): void {
    this.clockSource = "raf";
    let lastCount = -1;
    let lastTime = -1;
    const loop = (ts: number) => {
      if (!this.running) return;
      const count = this.video.getVideoPlaybackQuality?.().totalVideoFrames;
      const fresh = count !== undefined && count > 0 ? count !== lastCount : this.video.currentTime !== lastTime;
      lastCount = count ?? -1;
      lastTime = this.video.currentTime;
      if (fresh && this.video.readyState >= 2) this.grab(this.video, ts, null, count ?? null);
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  private runVideoFrame(Processor: ProcessorCtor): void {
    this.clockSource = "videoframe";
    const stream = this.video.srcObject as MediaStream;
    const track = stream.getVideoTracks()[0]!.clone();
    const reader = new Processor({ track }).readable.getReader();
    let offset: number | null = null;
    this.stopVideoFrame = () => {
      void reader.cancel();
      track.stop();
    };
    void (async () => {
      while (this.running) {
        const { value: frame, done } = await reader.read();
        if (done || !frame) break;
        const ts = frame.timestamp / 1000;
        offset ??= now() - ts; // mapped once, as SPEC 7.2 says
        this.grab(frame as unknown as CanvasImageSource, ts + offset, null, null);
        frame.close();
      }
    })();
  }

  private grab(source: CanvasImageSource, t: number, captureTime: number | null, presented: number | null): void {
    if (t <= this.lastT) return;
    if (Number.isFinite(this.lastT)) {
      this.intervals.push(t - this.lastT);
      if (this.intervals.length > 300) this.intervals.shift();
    }
    this.lastT = t;
    const vw = this.video.videoWidth;
    const vh = this.video.videoHeight;
    if (!vw || !vh) return;
    const i = this.i++;
    const cap = config.capture;
    const [w, h] = fitSize(vw, vh, this.opts.mobile ? cap.mobile_size : cap.desktop_size);
    const file = frameFile(i);
    const withFp = i % cap.fp_every === 0;
    const working = this.encoder.encode(source, w, h, cap.jpeg);
    let fp: Promise<Blob> | undefined;
    if (withFp) {
      const [fw, fh] = fitSize(vw, vh, cap.fp_max);
      fp = this.encoder.encode(source, fw, fh, cap.fp_jpeg);
    }
    this.opts.onFrame({
      meta: { i, t, capture_time: captureTime, presented_frames: presented, w, h, file, fp_file: withFp ? file : null },
      working,
      fp,
    });
  }
}
