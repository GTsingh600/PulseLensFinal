/**
 * Batched frame upload (SPEC 7.2): every upload_batch_ms, a bounded queue (queue_max working frames),
 * drop and log on overflow, never block capture. Frames go out in capture order: a batch is the longest
 * run of frames at the head of the queue whose JPEGs are ready.
 *
 * Multipart body (SPEC 6, POST /api/sessions/{id}/frames): `meta` = frames.jsonl lines for the batch,
 * `frames` = working JPEGs, `fp` = fingerprint JPEGs, each file named as in its meta line.
 */
import { config, type FrameMeta } from "@pulselens/types";
import type { GrabbedFrame } from "./grabber";

interface Entry {
  meta: FrameMeta;
  working?: Blob;
  fp?: Blob;
  needsFp: boolean;
  failed: boolean;
}

export interface UploaderOptions {
  post: (body: FormData) => Promise<void>;
  batchMs?: number;
  queueMax?: number;
}

export interface UploadStats {
  queued: number;
  uploaded: number;
  dropped: number;
  failedPosts: number;
}

export class FrameUploader {
  private queue: Entry[] = [];
  private timer: ReturnType<typeof setInterval> | undefined;
  private inFlight: Promise<void> | null = null;
  private readonly batchMs: number;
  private readonly queueMax: number;
  readonly stats: UploadStats = { queued: 0, uploaded: 0, dropped: 0, failedPosts: 0 };

  constructor(private readonly opts: UploaderOptions) {
    this.batchMs = opts.batchMs ?? config.capture.upload_batch_ms;
    this.queueMax = opts.queueMax ?? config.capture.queue_max;
  }

  start(): void {
    this.timer ??= setInterval(() => void this.flush(), this.batchMs);
  }

  /** Queues a frame; false (and counted as dropped) when the queue is full. */
  push(frame: GrabbedFrame): boolean {
    if (this.queue.length >= this.queueMax) {
      this.stats.dropped++;
      if (this.stats.dropped === 1 || this.stats.dropped % 30 === 0) {
        console.warn(`Upload queue full: ${this.stats.dropped} frame(s) dropped so far`);
      }
      return false;
    }
    const entry: Entry = { meta: frame.meta, needsFp: !!frame.fp, failed: false };
    this.queue.push(entry);
    this.stats.queued = this.queue.length;
    frame.working.then((b) => (entry.working = b), () => (entry.failed = true));
    frame.fp?.then((b) => (entry.fp = b), () => (entry.failed = true));
    return true;
  }

  private ready(e: Entry) {
    return e.failed || (!!e.working && (!e.needsFp || !!e.fp));
  }

  /** Sends the ready head of the queue. Concurrent calls share one request. */
  flush(): Promise<void> {
    this.inFlight ??= this.send().finally(() => (this.inFlight = null));
    return this.inFlight;
  }

  private async send(): Promise<void> {
    let n = 0;
    while (n < this.queue.length && this.ready(this.queue[n]!)) n++;
    if (!n) return;
    const batch = this.queue.slice(0, n);
    const good = batch.filter((e) => !e.failed);
    this.stats.dropped += batch.length - good.length;
    if (good.length) {
      const body = new FormData();
      body.append("meta", good.map((e) => JSON.stringify(e.meta)).join("\n") + "\n");
      for (const e of good) {
        body.append("frames", e.working!, e.meta.file);
        if (e.fp && e.meta.fp_file) body.append("fp", e.fp, e.meta.fp_file);
      }
      try {
        await this.opts.post(body);
      } catch (err) {
        this.stats.failedPosts++;
        console.warn("Frame upload failed; will retry", err);
        return; // the batch stays at the head of the queue
      }
      this.stats.uploaded += good.length;
    }
    this.queue.splice(0, n);
    this.stats.queued = this.queue.length;
  }

  /** Stops the timer and sends everything still queued (waiting for encodes; up to `retries` failures). */
  async stop(retries = 3): Promise<void> {
    clearInterval(this.timer);
    this.timer = undefined;
    let failures = 0;
    while (this.queue.length && failures <= retries) {
      const before = this.stats.failedPosts;
      await this.flush();
      if (this.stats.failedPosts > before) failures++;
      else if (this.queue.length && !this.ready(this.queue[0]!)) await new Promise((r) => setTimeout(r, 20));
    }
    this.stats.dropped += this.queue.length;
    this.queue = [];
    this.stats.queued = 0;
  }
}
