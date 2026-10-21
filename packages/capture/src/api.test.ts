// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, CaptureApi, CaptureSocket } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("CaptureApi", () => {
  it("posts JSON and parses the reply", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ session_id: "s1", ws_url: "/ws/session/s1" })));
    vi.stubGlobal("fetch", fetch);
    const out = await new CaptureApi("http://x").createSession({ mode: "superset", product: "lab" } as never);
    expect(out).toEqual({ session_id: "s1", ws_url: "/ws/session/s1" });
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://x/api/sessions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ mode: "superset", product: "lab" });
  });

  it("returns undefined for a 204 and throws ApiError with the status and body otherwise", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    await expect(new CaptureApi().finalize("s1", {})).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("bad frame file name", { status: 422 })));
    const err = await new CaptureApi().postFrames("s1", new FormData()).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.message).toContain("bad frame file name");
  });
});

class FakeWebSocket {
  static OPEN = 1;
  static last: FakeWebSocket;
  readyState = 0;
  sent: string[] = [];
  onopen?: () => void;
  onerror?: () => void;
  onclose?: () => void;
  onmessage?: (e: { data: string }) => void;
  constructor(readonly url: URL) {
    FakeWebSocket.last = this;
  }
  send(s: string) {
    this.sent.push(s);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
}

async function connected(role: "lab" | "customer" = "lab") {
  vi.stubGlobal("WebSocket", FakeWebSocket);
  const p = CaptureSocket.connect("/ws/session/s1", role);
  FakeWebSocket.last.open();
  return { socket: await p, ws: FakeWebSocket.last };
}

describe("CaptureSocket", () => {
  it("connects with ws:// on http pages and puts the role in the query", async () => {
    const { ws } = await connected("customer");
    expect(ws.url.protocol).toBe("ws:");
    expect(ws.url.pathname).toBe("/ws/session/s1");
    expect(ws.url.searchParams.get("role")).toBe("customer");
  });

  it("sends the session token for the lab role only, never for a customer", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    void CaptureSocket.connect("/ws/session/s1", "lab", "tok");
    expect(FakeWebSocket.last.url.searchParams.get("token")).toBe("tok");
    void CaptureSocket.connect("/ws/session/s1", "customer", "tok");
    expect(FakeWebSocket.last.url.searchParams.has("token")).toBe(false);
  });

  it("rejects when the socket fails to open", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const p = CaptureSocket.connect("/ws/session/s1", "lab");
    FakeWebSocket.last.onerror!();
    await expect(p).rejects.toThrow("failed to open");
  });

  it("keeps messages that arrive before a handler is attached, in order", async () => {
    const { socket, ws } = await connected();
    ws.onmessage!({ data: JSON.stringify({ type: "stage", stage: "camera" }) });
    ws.onmessage!({ data: JSON.stringify({ type: "prompt", key: "prompt.start" }) });
    const got: string[] = [];
    socket.onMessage = (m) => got.push(m.type);
    ws.onmessage!({ data: JSON.stringify({ type: "done", key: null }) });
    expect(got).toEqual(["stage", "prompt", "done"]);
  });

  it("ignores a message that is not JSON instead of throwing", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { socket, ws } = await connected();
    const got: unknown[] = [];
    socket.onMessage = (m) => got.push(m);
    ws.onmessage!({ data: "{oops" });
    expect(got).toEqual([]);
  });

  it("sends a heartbeat every 2 s, stops on close and never sends on a closed socket", async () => {
    vi.useFakeTimers();
    const { socket, ws } = await connected();
    vi.advanceTimersByTime(4100);
    expect(ws.sent.map((s) => JSON.parse(s).type)).toEqual(["heartbeat", "heartbeat"]);
    socket.close();
    vi.advanceTimersByTime(4000);
    socket.send({ type: "heartbeat", t: 1 });
    expect(ws.sent).toHaveLength(2);
  });

  it("calls onClose when the server closes the socket", async () => {
    const { socket, ws } = await connected();
    const closed = vi.fn();
    socket.onClose = closed;
    ws.close();
    expect(closed).toHaveBeenCalledOnce();
  });
});
