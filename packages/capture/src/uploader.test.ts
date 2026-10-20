import type { FrameMeta } from "@pulselens/types";
import { describe, expect, it, vi } from "vitest";
import type { GrabbedFrame } from "./grabber";
import { FrameUploader } from "./uploader";

const blob = () => new Blob(["x"], { type: "image/jpeg" });

function frame(i: number, fp = false, working: Promise<Blob> = Promise.resolve(blob())): GrabbedFrame {
  const file = `${String(i).padStart(6, "0")}.jpg`;
  const meta: FrameMeta = {
    i, t: i * 33, capture_time: null, presented_frames: i, w: 640, h: 480, file, fp_file: fp ? file : null,
  };
  return { meta, working, fp: fp ? Promise.resolve(blob()) : undefined };
}

function parts(fd: FormData) {
  const meta = String(fd.get("meta")).trim().split("\n").map((l) => JSON.parse(l) as FrameMeta);
  return { meta, frames: fd.getAll("frames") as File[], fp: fd.getAll("fp") as File[] };
}

describe("FrameUploader (SPEC 7.2)", () => {
  it("sends frames in capture order with meta lines, working and fingerprint files", async () => {
    const sent: FormData[] = [];
    const up = new FrameUploader({ post: async (fd) => void sent.push(fd), batchMs: 1e9 });
    for (let i = 0; i < 6; i++) up.push(frame(i, i % 5 === 0));
    await up.stop();
    const all = sent.map(parts);
    expect(all.flatMap((p) => p.meta.map((m) => m.i))).toEqual([0, 1, 2, 3, 4, 5]);
    expect(all.flatMap((p) => p.frames.map((f) => f.name))).toEqual([
      "000000.jpg", "000001.jpg", "000002.jpg", "000003.jpg", "000004.jpg", "000005.jpg",
    ]);
    expect(all.flatMap((p) => p.fp.map((f) => f.name))).toEqual(["000000.jpg", "000005.jpg"]);
    expect(up.stats).toMatchObject({ uploaded: 6, dropped: 0 });
  });

  it("drops new frames past the queue bound instead of blocking capture", () => {
    const up = new FrameUploader({ post: async () => {}, batchMs: 1e9, queueMax: 3 });
    const accepted = [0, 1, 2, 3, 4].map((i) => up.push(frame(i, false, new Promise<Blob>(() => {}))));
    expect(accepted).toEqual([true, true, true, false, false]);
    expect(up.stats.dropped).toBe(2);
  });

  it("flushes on a timer and keeps order while an earlier frame is still encoding", async () => {
    vi.useFakeTimers();
    const sent: number[][] = [];
    const up = new FrameUploader({ post: async (fd) => void sent.push(parts(fd).meta.map((m) => m.i)), batchMs: 1000 });
    let release!: (b: Blob) => void;
    up.push(frame(0, false, new Promise<Blob>((r) => (release = r))));
    up.push(frame(1));
    up.start();
    await vi.advanceTimersByTimeAsync(1000);
    expect(sent).toEqual([]); // frame 0 not encoded yet, so nothing goes out of order
    release(blob());
    await vi.advanceTimersByTimeAsync(1000);
    expect(sent).toEqual([[0, 1]]);
    await up.stop();
    vi.useRealTimers();
  });

  it("retries a failed batch and does not lose frames", async () => {
    let fail = true;
    const sent: number[] = [];
    const up = new FrameUploader({
      post: async (fd) => {
        if (fail) {
          fail = false;
          throw new Error("network");
        }
        sent.push(...parts(fd).meta.map((m) => m.i));
      },
      batchMs: 1e9,
    });
    up.push(frame(0));
    up.push(frame(1));
    await up.stop();
    expect(sent).toEqual([0, 1]);
  });
});
