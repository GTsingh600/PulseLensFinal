/**
 * One capture session on the customer or Lab device. The server drives it (SPEC 5, 6): it sends `stage`,
 * `prompt`, `pulse` and `done` messages; this class runs what each needs and reports back.
 *
 * start → create session → camera → grabber + uploader → details → WebSocket
 *   stage camera  → details posted → stage.done
 *   stage coach   → coaching rounds → stage.done with tips and metrics
 *   stage pulses  → light overlay up; each pulse is painted and acked
 *   done          → overlay down, grabber stopped, queue flushed, final details, finalize
 */
import type {
  CameraDetails, CaptureServerMessage, Channel, PulseAck, PulseMessage, RecordingLabel, SessionMode, Stage,
} from "@pulselens/types";
import { CaptureApi, CaptureSocket, type CaptureRole } from "./api";
import { openCamera, stopCamera, type OpenCamera, type StartResult } from "./camera";
import { loadFaceFinder, runCoaching, type CoachRound, type FaceFinder } from "./coaching";
import { collectCameraDetails, detectGyro, fpsFields } from "./details";
import { detectChannel, secureContextError } from "./env";
import { FrameGrabber, type GrabberSource } from "./grabber";
import { LightOverlay, LightPulseExecutor } from "./light";
import { FrameUploader } from "./uploader";

export type CapturePhase = "idle" | "starting" | "running" | "finalizing" | "done" | "error";

export interface CaptureState {
  phase: CapturePhase;
  sessionId: string | null;
  stage: Stage | null;
  /** explainer key of the current customer prompt */
  promptKey: string | null;
  channel: Channel | null;
  details: CameraDetails | null;
  coach: CoachRound[];
  frames: number;
  uploaded: number;
  dropped: number;
  pulses: number;
  acksOk: number;
  /** explainer key from the server's done message */
  doneKey: string | null;
  error: string | null;
}

export interface CaptureSessionOptions {
  video: HTMLVideoElement;
  product: "lab" | "demo";
  mode: SessionMode;
  role: CaptureRole;
  label?: RecordingLabel | null;
  scenario?: string | null;
  api?: CaptureApi;
  grabberSource?: GrabberSource;
  /** null disables the face detector (coaching then skips face tips) */
  faceFinder?: () => Promise<FaceFinder | null>;
  /** text for an explainer key, shown on the full-screen light overlay */
  promptText?: (key: string) => string;
  overlayParent?: HTMLElement;
  onChange?: (state: CaptureState) => void;
}

export class CaptureSession {
  state: CaptureState = {
    phase: "idle", sessionId: null, stage: null, promptKey: null, channel: null, details: null, coach: [],
    frames: 0, uploaded: 0, dropped: 0, pulses: 0, acksOk: 0, doneKey: null, error: null,
  };

  private readonly api: CaptureApi;
  private cam: OpenCamera | null = null;
  private grabber: FrameGrabber | null = null;
  private uploader: FrameUploader | null = null;
  private socket: CaptureSocket | null = null;
  private overlay: LightOverlay | null = null;
  private executor: LightPulseExecutor | null = null;
  private detailsPosted: Promise<void> | null = null;
  private statsTimer: ReturnType<typeof setInterval> | undefined;
  private startResult: StartResult | null = null;
  private finishing: Promise<void> | null = null;

  constructor(private readonly opts: CaptureSessionOptions) {
    this.api = opts.api ?? new CaptureApi();
  }

  private set(patch: Partial<CaptureState>): void {
    this.state = { ...this.state, ...patch };
    this.opts.onChange?.(this.state);
  }

  /** `startResult` comes from startTap(), called in the click handler before this. */
  async start(startResult: StartResult | null = null): Promise<void> {
    this.startResult = startResult;
    const insecure = secureContextError();
    if (insecure) return this.fail(insecure);
    this.set({ phase: "starting" });
    try {
      const nav = navigator as Navigator & { userAgentData?: { mobile: boolean } };
      const channel = detectChannel({
        ua: navigator.userAgent, uaMobile: nav.userAgentData?.mobile ?? null, maxTouchPoints: navigator.maxTouchPoints,
      });
      const created = await this.api.createSession({
        mode: this.opts.mode, product: this.opts.product, scenario: this.opts.scenario ?? null, label: this.opts.label ?? null,
      });
      this.set({ sessionId: created.session_id, channel });
      this.cam = await openCamera(this.opts.video);

      const sessionId = created.session_id;
      this.uploader = new FrameUploader({ post: (fd) => this.api.postFrames(sessionId, fd) });
      let firstFrame!: () => void;
      const gotFrame = new Promise<void>((r) => (firstFrame = r));
      this.grabber = new FrameGrabber(this.opts.video, {
        mobile: channel === "mobile_browser",
        source: this.opts.grabberSource,
        onFrame: (f) => {
          this.uploader!.push(f);
          firstFrame();
        },
      });
      this.grabber.start();
      this.uploader.start();
      this.statsTimer = setInterval(() => this.syncStats(), 500);

      this.detailsPosted = (async () => {
        const [gyro] = await Promise.all([detectGyro(startResult?.motionPermission ?? "not-needed"), gotFrame]);
        const details = await collectCameraDetails({
          track: this.cam!.track, channel, clockSource: this.grabber!.clockSource!, gyro, stats: this.grabber!.stats(),
        });
        this.set({ details });
        await this.api.postDetails(sessionId, details);
      })();

      this.socket = await CaptureSocket.connect(created.ws_url, this.opts.role, created.token);
      this.socket.onMessage = (msg, receivedAt) => void this.handle(msg, receivedAt).catch((e) => this.fail(e));
      this.socket.onClose = () => {
        if (this.state.phase === "running") this.fail("Connection to the server closed.");
      };
      this.set({ phase: "running" });
      await this.detailsPosted;
    } catch (e) {
      await this.fail(e);
    }
  }

  private syncStats(): void {
    const s = this.uploader?.stats;
    this.set({ frames: this.grabber?.stats().frames ?? 0, uploaded: s?.uploaded ?? 0, dropped: s?.dropped ?? 0 });
  }

  private async handle(msg: CaptureServerMessage, receivedAt: number): Promise<void> {
    switch (msg.type) {
      case "stage":
        this.set({ stage: msg.stage, promptKey: msg.prompt ?? null });
        if (msg.stage === "camera") {
          await this.detailsPosted;
          await this.postFpsUpdate();
          this.socket?.send({ type: "stage.done", stage: "camera", data: { details_posted: true } });
        } else if (msg.stage === "coach") {
          await this.coach();
        } else if (msg.stage === "pulses") {
          this.showOverlay();
        }
        return;
      case "prompt":
        this.set({ promptKey: msg.key });
        if (this.overlay) this.overlay.message.textContent = this.opts.promptText?.(msg.key) ?? "";
        return;
      case "pulse":
        return this.pulse(msg, receivedAt);
      case "done":
        return this.finish(msg.key);
      case "event":
        return; // lab role: the event stream, for screens that show it (M2.2 live plots)
    }
  }

  private async postFpsUpdate(): Promise<void> {
    if (!this.grabber || !this.state.channel || !this.state.sessionId) return;
    const update = { ...fpsFields(this.state.channel, this.grabber.stats()), clock_source: this.grabber.clockSource! };
    if (this.state.details) this.set({ details: { ...this.state.details, ...update } });
    await this.api.postDetails(this.state.sessionId, update);
  }

  private async coach(): Promise<void> {
    const findFace = await (this.opts.faceFinder ?? (() => loadFaceFinder()))();
    const rounds = await runCoaching(this.opts.video, {
      findFace,
      now: () => performance.now(),
      onTips: (round) => this.set({ coach: [...this.state.coach, round], promptKey: round.tips[0] ?? null }),
    });
    this.socket?.send({
      type: "stage.done", stage: "coach",
      data: { rounds: rounds.map((r) => ({ round: r.round, tips: r.tips, metrics: r.metrics })), face_detector: !!findFace },
    });
  }

  private showOverlay(): void {
    if (this.overlay) return;
    const mode = this.state.channel === "mobile_browser" ? "fullscreen" : "border";
    this.overlay = new LightOverlay({ mode });
    if (this.state.promptKey) this.overlay.message.textContent = this.opts.promptText?.(this.state.promptKey) ?? "";
    this.overlay.mount(this.opts.overlayParent ?? document.body);
    this.executor = new LightPulseExecutor(this.overlay);
  }

  private async pulse(msg: PulseMessage, receivedAt: number): Promise<void> {
    this.set({ pulses: this.state.pulses + 1 });
    let ack: PulseAck;
    if (msg.kind === "light") {
      this.showOverlay();
      ack = await this.executor!.run(msg, receivedAt);
    } else {
      // tilt, hand, lens and photo arrive with M2.2
      ack = {
        type: "ack", pulse_id: msg.pulse_id, sig: msg.sig, received: receivedAt, applied: null, painted: null, ended: null,
        ok: false, error: "unsupported_kind", shown: null,
      };
    }
    this.socket?.send(ack);
    if (ack.ok) this.set({ acksOk: this.state.acksOk + 1 });
  }

  /** Flushes everything and finalizes. Safe to call twice. */
  finish(doneKey: string | null = null): Promise<void> {
    this.finishing ??= (async () => {
      this.set({ phase: "finalizing", doneKey });
      this.overlay?.unmount();
      this.overlay = null;
      this.grabber?.stop();
      clearInterval(this.statsTimer);
      await this.uploader?.stop();
      this.syncStats();
      await this.postFpsUpdate();
      const id = this.state.sessionId!;
      await this.api.finalize(id, {
        frames: this.state.frames, uploaded: this.state.uploaded, dropped: this.state.dropped,
        pulses: this.state.pulses, acks_ok: this.state.acksOk, start: this.startResult,
      });
      this.cleanup();
      this.set({ phase: "done" });
    })().catch((e) => this.fail(e));
    return this.finishing;
  }

  private cleanup(): void {
    clearInterval(this.statsTimer);
    this.socket?.close();
    this.socket = null;
    this.overlay?.unmount();
    this.overlay = null;
    this.grabber?.close();
    stopCamera(this.cam, this.opts.video);
    this.cam = null;
  }

  async fail(e: unknown): Promise<void> {
    const error = e instanceof Error ? e.message : String(e);
    console.error("Capture session failed:", e);
    this.cleanup();
    this.set({ phase: "error", error });
  }
}
