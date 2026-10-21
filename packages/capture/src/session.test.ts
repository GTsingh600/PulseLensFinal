// @vitest-environment jsdom
// CaptureSession as a state machine: every collaborator is replaced, so each server message can be driven by hand.
import type { CaptureClientMessage, CaptureServerMessage } from "@pulselens/types";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sockets: FakeSocket[] = [];

class FakeSocket {
  sent: CaptureClientMessage[] = [];
  closed = false;
  onClose?: () => void;
  handler?: (msg: CaptureServerMessage, at: number) => void;
  set onMessage(h: (msg: CaptureServerMessage, at: number) => void) {
    this.handler = h;
  }
  send(msg: CaptureClientMessage) {
    this.sent.push(msg);
  }
  close() {
    this.closed = true;
  }
  /** a server message, then wait for the session to finish handling it */
  async push(msg: object) {
    this.handler!(msg as CaptureServerMessage, 1000);
    await vi.waitFor(() => undefined);
    await new Promise((r) => setTimeout(r, 0));
  }
}

const run = vi.fn();
vi.mock("./api", () => ({
  CaptureSocket: {
    connect: vi.fn(async () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s;
    }),
  },
}));
vi.mock("./camera", () => ({
  openCamera: vi.fn(async () => ({ stream: { getTracks: () => [] }, track: { label: "cam" } })),
  stopCamera: vi.fn(),
}));
vi.mock("./grabber", () => ({
  FrameGrabber: class {
    clockSource = "captureTime";
    constructor(_v: unknown, private o: { onFrame: (f: object) => void }) {}
    start() {
      this.o.onFrame({ i: 0 });
    }
    stop() {}
    close() {}
    stats() {
      return { frames: 12, fpsMedian: 29.9, jitterMs: 1.1 };
    }
  },
}));
vi.mock("./uploader", () => ({
  FrameUploader: class {
    stats = { uploaded: 12, dropped: 0 };
    push() {}
    start() {}
    async stop() {}
  },
}));
vi.mock("./light", () => ({
  LightOverlay: class {
    message = document.createElement("p");
    mount() {}
    unmount() {}
  },
  LightPulseExecutor: class {
    run = run;
  },
}));
vi.mock("./coaching", () => ({
  loadFaceFinder: vi.fn(async () => null),
  runCoaching: vi.fn(async (_v: unknown, o: { onTips: (r: object) => void }) => {
    const round = { round: 1, tips: ["tip.light"], metrics: { luma: 0.4 } };
    o.onTips(round);
    return [round];
  }),
}));
vi.mock("./details", () => ({
  collectCameraDetails: vi.fn(async () => ({ channel: "desktop_browser", browser: "Brave 155" })),
  detectGyro: vi.fn(async () => "absent"),
  fpsFields: () => ({ fps_median: 29.9, fps_jitter_ms: 1.1, profile_measured: "desktop_browser|ge27" }),
}));

const { CaptureSession } = await import("./session");

function fakeApi(overrides: Record<string, unknown> = {}) {
  return {
    createSession: vi.fn(async () => ({ session_id: "s1", ws_url: "/ws/session/s1", pair_code: null })),
    postDetails: vi.fn(async () => undefined),
    postFrames: vi.fn(async () => undefined),
    finalize: vi.fn(async () => undefined),
    ...overrides,
  };
}

function newSession(api = fakeApi()) {
  const states: string[] = [];
  const s = new CaptureSession({
    video: document.createElement("video"),
    product: "lab",
    mode: "superset",
    role: "lab",
    api: api as never,
    promptText: (k) => `text for ${k}`,
    onChange: (st) => states.push(st.phase),
  });
  return { s, api, states };
}

const PULSE = { type: "pulse", pulse_id: "s1-0", kind: "light", source: "orchestrator", params: { mode: "colour" }, sig: "x" };

beforeEach(() => {
  sockets.length = 0;
  run.mockReset();
  run.mockImplementation(async (msg: { pulse_id: string; sig: string }) => ({
    type: "ack", pulse_id: msg.pulse_id, sig: msg.sig, received: 1000, applied: 1001, painted: 1002, ended: 1402, ok: true,
    error: null, shown: null,
  }));
  vi.stubGlobal("isSecureContext", true);
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: vi.fn() }, configurable: true });
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => vi.unstubAllGlobals());

describe("CaptureSession", () => {
  it("refuses to start outside a secure context and never creates a session", async () => {
    vi.stubGlobal("isSecureContext", false);
    const { s, api } = newSession();
    await s.start();
    expect(s.state.phase).toBe("error");
    expect(s.state.error).toMatch(/HTTPS/);
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it("runs camera, coach, pulses and done in order, and finalizes with the counts", async () => {
    const { s, api, states } = newSession();
    await s.start();
    expect(s.state.phase).toBe("running");
    expect(s.state.details).toMatchObject({ browser: "Brave 155" });
    const ws = sockets[0]!;

    await ws.push({ type: "stage", stage: "camera", prompt: null });
    expect(ws.sent.at(-1)).toEqual({ type: "stage.done", stage: "camera", data: { details_posted: true } });
    expect(api.postDetails).toHaveBeenCalledTimes(2); // full details, then the fps update

    await ws.push({ type: "stage", stage: "coach", prompt: null });
    expect(ws.sent.at(-1)).toMatchObject({ type: "stage.done", stage: "coach", data: { face_detector: false } });
    expect(s.state.coach).toHaveLength(1);
    expect(s.state.promptKey).toBe("tip.light");

    await ws.push({ type: "stage", stage: "pulses", prompt: "prompt.still" });
    await ws.push(PULSE);
    await ws.push({ ...PULSE, pulse_id: "s1-1" });
    expect(ws.sent.filter((m) => m.type === "ack")).toHaveLength(2);
    expect(s.state).toMatchObject({ pulses: 2, acksOk: 2 });

    await ws.push({ type: "done", key: "done.thanks" });
    await vi.waitFor(() => expect(s.state.phase).toBe("done"));
    expect(api.finalize).toHaveBeenCalledWith(
      "s1",
      expect.objectContaining({ frames: 12, uploaded: 12, dropped: 0, pulses: 2, acks_ok: 2 }),
    );
    expect(ws.closed).toBe(true);
    expect(states).toEqual(expect.arrayContaining(["starting", "running", "finalizing", "done"]));
    expect(states.indexOf("finalizing")).toBeLessThan(states.lastIndexOf("done"));
  });

  it("acks a pulse kind it cannot run yet with ok false, so the server logs it", async () => {
    const { s } = newSession();
    await s.start();
    await sockets[0]!.push({ ...PULSE, kind: "tilt" });
    expect(sockets[0]!.sent.at(-1)).toMatchObject({ type: "ack", ok: false, error: "unsupported_kind" });
    expect(s.state).toMatchObject({ pulses: 1, acksOk: 0 });
  });

  it("does not count a failed light pulse as answered", async () => {
    run.mockResolvedValueOnce({ type: "ack", pulse_id: "s1-0", sig: "x", ok: false, error: "flash_limit" });
    const { s } = newSession();
    await s.start();
    await sockets[0]!.push(PULSE);
    expect(s.state).toMatchObject({ pulses: 1, acksOk: 0 });
  });

  it("fails cleanly when the server drops the connection mid-session", async () => {
    const { s } = newSession();
    await s.start();
    sockets[0]!.onClose!();
    await vi.waitFor(() => expect(s.state.phase).toBe("error"));
    expect(s.state.error).toBe("Connection to the server closed.");
  });

  it("ignores the socket closing after it has finished", async () => {
    const { s } = newSession();
    await s.start();
    await sockets[0]!.push({ type: "done", key: null });
    await vi.waitFor(() => expect(s.state.phase).toBe("done"));
    sockets[0]!.onClose!();
    expect(s.state.phase).toBe("done");
  });

  it("finalizes once even when done arrives twice", async () => {
    const { s, api } = newSession();
    await s.start();
    await sockets[0]!.push({ type: "done", key: null });
    await sockets[0]!.push({ type: "done", key: null });
    await vi.waitFor(() => expect(s.state.phase).toBe("done"));
    expect(api.finalize).toHaveBeenCalledTimes(1);
  });

  it("reports a server error on create without opening the camera", async () => {
    const { openCamera } = await import("./camera");
    vi.mocked(openCamera).mockClear();
    const { s } = newSession(fakeApi({ createSession: vi.fn(async () => Promise.reject(new Error("POST /api/sessions → 500"))) }));
    await s.start();
    expect(s.state).toMatchObject({ phase: "error", error: "POST /api/sessions → 500" });
    expect(openCamera).not.toHaveBeenCalled();
  });

  it("turns an exception while handling a pulse into an error, not a stuck session", async () => {
    run.mockRejectedValueOnce(new Error("overlay gone"));
    const { s } = newSession();
    await s.start();
    await sockets[0]!.push(PULSE);
    await vi.waitFor(() => expect(s.state.phase).toBe("error"));
    expect(s.state.error).toBe("overlay gone");
  });
});
